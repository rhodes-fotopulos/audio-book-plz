"""Abstract TTS engine interface for audio-book-plz.

Defines the contract that all TTS engines (Qwen3-TTS, Chatterbox) must
implement.  The ``AudioResult`` dataclass provides a uniform numpy-based
return type so no framework-specific types (torch.Tensor, mx.array) leak
beyond the engine boundary.

The ``save_wav_atomic`` method and ``ensure_ollama_unloaded`` helper are
concrete on the base class — shared by all engines.
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np

from src.synthesis.models import SynthesisConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Uniform audio result — no torch or mlx types leak past this boundary
# ---------------------------------------------------------------------------


@dataclass
class AudioResult:
    """Audio output from any TTS engine.

    All engines convert their native format (torch.Tensor, mx.array) into
    a numpy float32 array before returning.  This lets downstream code
    (save, assembly, metrics) stay framework-agnostic.
    """

    audio: np.ndarray
    """1-D float32 numpy array of audio samples."""

    sample_rate: int
    """Audio sample rate in Hz (e.g. 24000)."""

    duration_s: float
    """Duration of the audio in seconds."""


# ---------------------------------------------------------------------------
# Abstract engine interface
# ---------------------------------------------------------------------------


class TTSEngineBase(ABC):
    """Contract for TTS engines used by the synthesis pipeline.

    Subclasses:
    - ``ChatterboxEngine`` — PyTorch/MPS, Chatterbox 500M
    - ``QwenTTSEngine`` — MLX/Metal, Qwen3-TTS 1.7B Base

    Usage::

        engine = create_engine(config)    # via engine_factory
        engine.load_model()
        result = engine.generate("Hello.", "ref.wav", "Hello there.")
        engine.save_wav_atomic(result, "output/seg_0000.wav")
        engine.unload()
    """

    def __init__(self, config: SynthesisConfig) -> None:
        self.config = config

    # ------------------------------------------------------------------
    # Abstract methods — each engine MUST implement
    # ------------------------------------------------------------------

    @abstractmethod
    def load_model(self) -> None:
        """Load the TTS model into memory."""

    @abstractmethod
    def generate(
        self,
        text: str,
        ref_clip_path: str,
        ref_transcript: str | None = None,
        segment_type: str = "narration",
    ) -> AudioResult:
        """Generate audio for *text* using the reference voice clip.

        Args:
            text: Speech-ready text to synthesise.
            ref_clip_path: Path to reference voice WAV clip.
            ref_transcript: Transcript of the reference clip (Qwen3-TTS
                uses this for better cloning; Chatterbox ignores it).
            segment_type: ``'narration'`` or ``'dialogue'``.

        Returns:
            ``AudioResult`` with numpy audio data.
        """

    @abstractmethod
    def cleanup_memory(self) -> None:
        """Release caches / buffers without unloading the model."""

    @abstractmethod
    def unload(self) -> None:
        """Fully release the model and free all associated memory."""

    @property
    @abstractmethod
    def sample_rate(self) -> int:
        """Audio sample rate reported by the loaded model."""

    @property
    @abstractmethod
    def engine_name(self) -> str:
        """Short identifier, e.g. ``'qwen3-tts-1.7b'``, ``'chatterbox-500m'``."""

    @property
    @abstractmethod
    def engine_version(self) -> str:
        """Library version string for checkpoint tagging."""

    # ------------------------------------------------------------------
    # Concrete helpers — shared by all engines
    # ------------------------------------------------------------------

    def save_wav_atomic(self, audio: AudioResult, output_path: str) -> bool:
        """Save audio atomically with duration validation.

        Writes to a ``.tmp`` file first, validates duration meets the
        minimum threshold, then performs an atomic rename.  Uses
        ``soundfile`` for framework-agnostic WAV writing.

        Returns:
            True if saved successfully, False if duration check failed.
        """
        import soundfile as sf

        if audio.duration_s < self.config.min_wav_duration_s:
            logger.warning(
                "WAV duration %.3fs below minimum %.3fs — skipping %s",
                audio.duration_s,
                self.config.min_wav_duration_s,
                output_path,
            )
            return False

        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        tmp_path = output_path + ".tmp"
        sf.write(tmp_path, audio.audio, audio.sample_rate)
        os.rename(tmp_path, output_path)
        return True

    def ensure_ollama_unloaded(self) -> None:
        """Unload any Ollama models to free GPU memory before TTS.

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
