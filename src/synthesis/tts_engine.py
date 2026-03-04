"""Backward-compatible shim for the old TTSEngine class.

This module preserves the ``TTSEngine`` import for code that still
references it (e.g. ``src/assembly/announcer.py``).  New code should
use ``create_engine()`` from ``src.synthesis.engine_factory`` instead.

The shim wraps ``ChatterboxEngine`` behind the original ``TTSEngine``
name and API surface.
"""

from __future__ import annotations

import logging
import warnings

from src.synthesis.chatterbox_engine import ChatterboxEngine
from src.synthesis.models import SynthesisConfig

logger = logging.getLogger(__name__)


class TTSEngine(ChatterboxEngine):
    """Legacy wrapper — delegates to ChatterboxEngine.

    .. deprecated::
        Use ``create_engine(config)`` from ``src.synthesis.engine_factory``
        instead.
    """

    def __init__(self, config: SynthesisConfig) -> None:
        warnings.warn(
            "TTSEngine is deprecated — use create_engine() from "
            "src.synthesis.engine_factory instead",
            DeprecationWarning,
            stacklevel=2,
        )
        super().__init__(config)
