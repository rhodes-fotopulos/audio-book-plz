"""Qwen3-TTS engine — MLX/Metal implementation via mlx-audio.

Wraps Qwen3-TTS 1.7B Base model for voice cloning on Apple Silicon.
Uses mlx-audio's ``load_model`` + ``model.generate`` API with
``ref_audio`` / ``ref_text`` parameters for high-quality cloning.

All heavy imports (mlx, mlx_audio, numpy, soundfile) happen inside
methods to avoid loading them at module import time.
"""

from __future__ import annotations

import importlib.metadata
import logging
from typing import Any

from src.synthesis.engine_base import AudioResult, TTSEngineBase
from src.synthesis.models import SynthesisConfig

logger = logging.getLogger(__name__)

# Model identifier on HuggingFace / mlx-community
_MODEL_ID = "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16"


class QwenTTSEngine(TTSEngineBase):
    """Qwen3-TTS 1.7B Base model via mlx-audio on Apple Silicon.

    Usage::

        engine = QwenTTSEngine(SynthesisConfig(engine_type='qwen3'))
        engine.load_model()
        result = engine.generate(
            "Hello world.",
            "ref.wav",
            ref_transcript="Hello there.",
        )
        engine.save_wav_atomic(result, "output/seg_0000.wav")
        engine.unload()
    """

    def __init__(self, config: SynthesisConfig) -> None:
        super().__init__(config)
        self.model = None
        self._sample_rate: int | None = None
        self._ref_cache: dict[str, Any] = {}
        self._encode_cache: dict[int, Any] | None = None

    # ------------------------------------------------------------------
    # Model loading
    # ------------------------------------------------------------------

    def load_model(self) -> None:
        """Load Qwen3-TTS 1.7B Base via mlx-audio with Metal cache limit."""
        self.ensure_ollama_unloaded()

        import mlx.core as mx
        from mlx_audio.tts.utils import load_model

        # Set Metal cache limit before loading model
        cache_bytes = int(self.config.mlx_cache_limit_gb * 1024**3)
        mx.metal.set_cache_limit(cache_bytes)
        logger.info(
            "MLX Metal cache limit set to %.1f GB", self.config.mlx_cache_limit_gb
        )

        logger.info("Loading Qwen3-TTS 1.7B Base from %s...", _MODEL_ID)
        self.model = load_model(_MODEL_ID)

        self._sample_rate = getattr(self.model, "sample_rate", None)
        if self._sample_rate is None or self._sample_rate <= 0:
            # Fallback — Qwen3-TTS typically outputs at 24000 Hz
            logger.warning(
                "Could not determine sample rate from model; defaulting to 24000 Hz"
            )
            self._sample_rate = 24000

        # Wrap speech_tokenizer.encode with identity-based cache
        if hasattr(self.model, "speech_tokenizer") and hasattr(self.model.speech_tokenizer, "encode"):
            original_encode = self.model.speech_tokenizer.encode
            encode_cache: dict[int, Any] = {}

            def cached_encode(audio: Any) -> Any:
                key = id(audio)
                if key not in encode_cache:
                    encode_cache[key] = original_encode(audio)
                return encode_cache[key]

            self.model.speech_tokenizer.encode = cached_encode
            self._encode_cache = encode_cache

        logger.info(
            "Qwen3-TTS 1.7B loaded on MLX Metal (sample rate: %d Hz)",
            self._sample_rate,
        )

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    def generate(
        self,
        text: str,
        ref_clip_path: str,
        ref_transcript: str | None = None,
        segment_type: str = "narration",
        *,
        character_name: str | None = None,
    ) -> AudioResult:
        """Generate audio for *text* using the reference voice clip.

        Args:
            text: Speech-ready text to synthesise.
            ref_clip_path: Path to reference voice WAV clip.
            ref_transcript: Transcript of the reference clip.  Providing
                this significantly improves voice cloning quality.
            segment_type: ``'narration'`` or ``'dialogue'`` (currently
                unused by Qwen3-TTS Base model).
            character_name: Character name for reference audio caching.
                When provided, the reference audio is loaded once and
                reused for all segments of the same character.

        Returns:
            ``AudioResult`` with numpy audio data.
        """
        import numpy as np

        if self.model is None:
            raise RuntimeError("Model not loaded — call load_model() first")

        if ref_transcript is None:
            logger.warning(
                "No transcript provided for voice cloning — quality may be reduced"
            )

        # Two-layer cache: Layer 1 — load_audio cache
        cache_key = character_name or ref_clip_path
        if cache_key in self._ref_cache:
            ref_audio_data = self._ref_cache[cache_key]
            logger.debug("Using cached reference for %s", cache_key)
        else:
            from mlx_audio.utils import load_audio

            ref_audio_data = load_audio(ref_clip_path, sample_rate=self._sample_rate)
            self._ref_cache[cache_key] = ref_audio_data
            logger.info("Cached reference encoding for %s", cache_key)

        results = list(
            self.model.generate(
                text=text,
                ref_audio=ref_audio_data,
                ref_text=ref_transcript,
            )
        )

        audio_mx = results[0].audio

        # Convert mx.array -> numpy float32
        audio_np = np.array(audio_mx, dtype=np.float32)
        if audio_np.ndim == 2:
            audio_np = audio_np.squeeze(0)

        duration = len(audio_np) / self._sample_rate

        return AudioResult(
            audio=audio_np,
            sample_rate=self._sample_rate,
            duration_s=duration,
        )

    # ------------------------------------------------------------------
    # Memory management
    # ------------------------------------------------------------------

    def cleanup_memory(self) -> None:
        """Clear MLX Metal cache and log memory stats."""
        import mlx.core as mx

        mx.metal.clear_cache()

        active_mb = mx.metal.get_active_memory() / (1024**2)
        peak_mb = mx.metal.get_peak_memory() / (1024**2)
        logger.debug(
            "MLX memory after cleanup: active=%.1f MB, peak=%.1f MB",
            active_mb,
            peak_mb,
        )

    def unload(self) -> None:
        """Release the Qwen3-TTS model and free Metal memory."""
        self._ref_cache.clear()
        if self._encode_cache is not None:
            self._encode_cache.clear()
        self.model = None
        self.cleanup_memory()
        logger.info("Qwen3-TTS model unloaded")

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def sample_rate(self) -> int:
        if self._sample_rate is None:
            raise RuntimeError("Model not loaded — call load_model() first")
        return self._sample_rate

    @property
    def engine_name(self) -> str:
        return "qwen3-tts-1.7b"

    @property
    def engine_version(self) -> str:
        try:
            return importlib.metadata.version("mlx-audio")
        except importlib.metadata.PackageNotFoundError:
            return "unknown"
