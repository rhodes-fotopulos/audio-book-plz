"""Chatterbox TTS engine wrapper with Apple Silicon MPS support.

Handles the full model lifecycle: Ollama unload -> load to CPU ->
MPS migration -> generate -> atomic WAV save -> memory cleanup.

All heavy imports (torch, torchaudio, chatterbox) happen inside
methods to avoid loading them at module import time.  This keeps
``python main.py --help`` fast.
"""

from __future__ import annotations

import gc
import logging
import os
from typing import TYPE_CHECKING

from src.synthesis.models import SynthesisConfig

if TYPE_CHECKING:
    import torch

logger = logging.getLogger(__name__)


class TTSEngine:
    """Wraps Chatterbox TTS with MPS-safe loading and memory management.

    Usage::

        engine = TTSEngine(SynthesisConfig())
        engine.load_model()         # loads Chatterbox, migrates to MPS
        wav = engine.generate("Hello world.", "ref.wav")
        engine.save_wav_atomic(wav, "output/seg_0000.wav")
        engine.unload()
    """

    def __init__(self, config: SynthesisConfig) -> None:
        self.config = config
        self.model = None  # ChatterboxTTS instance (lazy)
        self.device: str | None = None
        self._torch = None  # cached torch module
        self._torchaudio = None  # cached torchaudio module

    # ------------------------------------------------------------------
    # Ollama cleanup
    # ------------------------------------------------------------------

    def ensure_ollama_unloaded(self) -> None:
        """Unload any Ollama models to free GPU memory before Chatterbox.

        Calls the existing ``unload_model()`` helper from the attribution
        package and additionally checks ``ollama.list()`` for any models
        still resident.  Connection errors are silently ignored (Ollama
        may not be running).
        """
        # Use the existing unload helper from Phase 2
        try:
            from src.attribution.llm_client import unload_model

            unload_model()
            logger.info("Ollama default model unload requested")
        except Exception as exc:
            logger.debug("Could not call unload_model: %s", exc)

        # Also check for any other loaded models via the Ollama API
        try:
            import ollama

            running = ollama.list()
            models = getattr(running, "models", None) or []
            for m in models:
                name = getattr(m, "name", None) or getattr(m, "model", str(m))
                try:
                    from src.attribution.llm_client import unload_model as _unload

                    _unload(model=str(name))
                    logger.info("Unloaded Ollama model: %s", name)
                except Exception:
                    pass
        except Exception as exc:
            logger.debug("Ollama not reachable or list failed: %s", exc)

    # ------------------------------------------------------------------
    # Model loading
    # ------------------------------------------------------------------

    def load_model(self) -> None:
        """Load Chatterbox TTS with CPU-first strategy and MPS migration.

        Sets ``PYTORCH_ENABLE_MPS_FALLBACK=1`` before any torch import so
        unsupported ops (FFT) fall back to CPU transparently.

        Steps:
        1. Unload any resident Ollama models.
        2. Load Chatterbox weights to CPU.
        3. Detect best device (MPS > CPU).
        4. Migrate model components individually to MPS if available.
        """
        # MUST be set before torch is imported
        os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"

        self.ensure_ollama_unloaded()

        # Late imports — keeps module-level import free of torch
        import torch
        import torchaudio  # noqa: F401 — ensure torchaudio is loaded

        self._torch = torch
        try:
            self._torchaudio = torchaudio
        except Exception:
            pass

        from chatterbox.tts import ChatterboxTTS

        logger.info("Loading Chatterbox TTS to CPU...")
        model = ChatterboxTTS.from_pretrained("cpu")

        # Device detection
        if self.config.device == "auto":
            device = "mps" if torch.backends.mps.is_available() else "cpu"
        else:
            device = self.config.device

        # Component-wise MPS migration (avoids MPS tensor allocation errors)
        if device == "mps":
            for attr_name in ("t3", "s3gen", "ve"):
                component = getattr(model, attr_name, None)
                if component is not None:
                    setattr(model, attr_name, component.to(device))
                    logger.debug("Migrated model.%s to %s", attr_name, device)
            model.device = device
            logger.info("Chatterbox loaded on MPS (Apple Silicon GPU)")
        else:
            logger.info("Chatterbox loaded on CPU")

        self.model = model
        self.device = device
        logger.info("Sample rate: %d Hz", self.model.sr)

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    def generate(
        self,
        text: str,
        ref_clip_path: str,
        segment_type: str = "narration",
        exaggeration: float | None = None,
        cfg_weight: float | None = None,
    ) -> "torch.Tensor":
        """Generate audio for a single text segment.

        Args:
            text: Speech-ready text (ideally <= 280 chars).
            ref_clip_path: Path to reference voice WAV clip.
            segment_type: 'narration' or 'dialogue' — selects defaults.
            exaggeration: Override exaggeration (None = use config default).
            cfg_weight: Override CFG weight (None = use config default).

        Returns:
            Audio waveform tensor.
        """
        if self.model is None:
            raise RuntimeError("Model not loaded — call load_model() first")

        if exaggeration is None:
            exaggeration = (
                self.config.dialogue_exaggeration
                if segment_type == "dialogue"
                else self.config.narration_exaggeration
            )
        if cfg_weight is None:
            cfg_weight = self.config.cfg_weight

        wav = self.model.generate(
            text,
            audio_prompt_path=ref_clip_path,
            exaggeration=exaggeration,
            cfg_weight=cfg_weight,
        )
        return wav

    # ------------------------------------------------------------------
    # Atomic WAV writing
    # ------------------------------------------------------------------

    def save_wav_atomic(self, wav_tensor: "torch.Tensor", output_path: str) -> bool:
        """Save a WAV file atomically with duration validation.

        Writes to a ``.tmp`` file first, validates duration meets the
        minimum threshold, then performs an atomic rename.  This prevents
        corrupted partial files from interrupted writes.

        Returns:
            True if saved successfully, False if duration check failed.
        """
        import torchaudio as ta

        duration = wav_tensor.shape[-1] / self.model.sr
        if duration < self.config.min_wav_duration_s:
            logger.warning(
                "WAV duration %.3fs below minimum %.3fs — skipping %s",
                duration,
                self.config.min_wav_duration_s,
                output_path,
            )
            return False

        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        tmp_path = output_path + ".tmp"
        ta.save(tmp_path, wav_tensor, self.model.sr)
        os.rename(tmp_path, output_path)
        return True

    # ------------------------------------------------------------------
    # Memory management
    # ------------------------------------------------------------------

    def cleanup_memory(self) -> None:
        """Aggressive memory cleanup to mitigate Chatterbox memory leak.

        Combines Python garbage collection with device-specific cache
        clearing.  Should be called every ``config.cleanup_interval``
        segments during synthesis.
        """
        gc.collect()
        if self._torch is not None:
            if self.device == "mps":
                self._torch.mps.empty_cache()
            elif self.device == "cuda":
                self._torch.cuda.empty_cache()

    @property
    def sample_rate(self) -> int:
        """Audio sample rate reported by the loaded model."""
        if self.model is None:
            raise RuntimeError("Model not loaded — call load_model() first")
        return self.model.sr

    def unload(self) -> None:
        """Release the model and free all associated memory."""
        self.model = None
        self.cleanup_memory()
        gc.collect()
        logger.info("Chatterbox model unloaded")
