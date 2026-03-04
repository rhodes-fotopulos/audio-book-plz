"""TTS engine factory — creates the right engine from config.

Lazy imports keep heavy dependencies (torch OR mlx) from loading until
the selected engine is actually instantiated.
"""

from __future__ import annotations

import logging

from src.synthesis.engine_base import TTSEngineBase
from src.synthesis.models import SynthesisConfig

logger = logging.getLogger(__name__)

_SUPPORTED_ENGINES = ("qwen3", "chatterbox")


def create_engine(config: SynthesisConfig) -> TTSEngineBase:
    """Create a TTS engine instance based on ``config.engine_type``.

    Args:
        config: Synthesis configuration with ``engine_type`` set.

    Returns:
        An unloaded engine — caller must call ``engine.load_model()``.

    Raises:
        ValueError: If ``engine_type`` is not recognised.
    """
    engine_type = config.engine_type.lower()

    if engine_type == "qwen3":
        from src.synthesis.qwen_engine import QwenTTSEngine

        logger.info("Creating Qwen3-TTS engine")
        return QwenTTSEngine(config)

    if engine_type == "chatterbox":
        from src.synthesis.chatterbox_engine import ChatterboxEngine

        logger.info("Creating Chatterbox engine")
        return ChatterboxEngine(config)

    raise ValueError(
        f"Unknown engine_type '{config.engine_type}'. "
        f"Supported: {', '.join(_SUPPORTED_ENGINES)}"
    )
