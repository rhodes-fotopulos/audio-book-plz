"""Chatterbox TTS engine — PyTorch/MPS implementation.

Wraps the Chatterbox 500M model behind the ``TTSEngineBase`` interface
so it can be used as a fallback engine when Qwen3-TTS fails or when
the user explicitly selects ``engine_type='chatterbox'``.

All heavy imports (torch, torchaudio, chatterbox) happen inside methods
to avoid loading them at module import time.
"""

from __future__ import annotations

import gc
import importlib.metadata
import logging
import os
from typing import TYPE_CHECKING

from src.synthesis.engine_base import AudioResult, TTSEngineBase
from src.synthesis.models import SynthesisConfig

if TYPE_CHECKING:
    import torch

logger = logging.getLogger(__name__)


class ChatterboxEngine(TTSEngineBase):
    """Chatterbox TTS with MPS-safe loading and memory management.

    Usage::

        engine = ChatterboxEngine(SynthesisConfig(engine_type='chatterbox'))
        engine.load_model()
        result = engine.generate("Hello world.", "ref.wav")
        engine.save_wav_atomic(result, "output/seg_0000.wav")
        engine.unload()
    """

    def __init__(self, config: SynthesisConfig) -> None:
        super().__init__(config)
        self.model = None  # ChatterboxTTS instance (lazy)
        self.device: str | None = None
        self._torch = None  # cached torch module
        self._torchaudio = None  # cached torchaudio module

    # ------------------------------------------------------------------
    # Model loading
    # ------------------------------------------------------------------

    def load_model(self) -> None:
        """Load Chatterbox TTS with CPU-first strategy and MPS migration.

        Sets ``PYTORCH_ENABLE_MPS_FALLBACK=1`` before any torch import so
        unsupported ops (FFT) fall back to CPU transparently.
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
        ref_transcript: str | None = None,
        segment_type: str = "narration",
        exaggeration: float | None = None,
        cfg_weight: float | None = None,
    ) -> AudioResult:
        """Generate audio for a single text segment.

        Args:
            text: Speech-ready text (ideally <= 280 chars).
            ref_clip_path: Path to reference voice WAV clip.
            ref_transcript: Ignored — Chatterbox does not use transcripts.
            segment_type: ``'narration'`` or ``'dialogue'`` — selects defaults.
            exaggeration: Override exaggeration (None = use config default).
            cfg_weight: Override CFG weight (None = use config default).

        Returns:
            ``AudioResult`` with numpy audio data.
        """
        import numpy as np

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

        # Convert torch.Tensor -> numpy for uniform AudioResult
        audio_np = np.array(wav.cpu().numpy(), dtype=np.float32)
        if audio_np.ndim == 2:
            audio_np = audio_np.squeeze(0)

        duration = len(audio_np) / self.model.sr

        return AudioResult(
            audio=audio_np,
            sample_rate=self.model.sr,
            duration_s=duration,
        )

    # ------------------------------------------------------------------
    # Memory management
    # ------------------------------------------------------------------

    def cleanup_memory(self) -> None:
        """Aggressive memory cleanup to mitigate Chatterbox memory leak.

        Combines Python garbage collection with device-specific cache
        clearing.
        """
        gc.collect()
        if self._torch is not None:
            if self.device == "mps":
                self._torch.mps.empty_cache()
            elif self.device == "cuda":
                self._torch.cuda.empty_cache()

    def unload(self) -> None:
        """Release the model and free all associated memory."""
        self.model = None
        self.cleanup_memory()
        gc.collect()
        logger.info("Chatterbox model unloaded")

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def sample_rate(self) -> int:
        """Audio sample rate reported by the loaded model."""
        if self.model is None:
            raise RuntimeError("Model not loaded — call load_model() first")
        return self.model.sr

    @property
    def engine_name(self) -> str:
        return "chatterbox-500m"

    @property
    def engine_version(self) -> str:
        try:
            return importlib.metadata.version("chatterbox-tts")
        except importlib.metadata.PackageNotFoundError:
            return "unknown"
