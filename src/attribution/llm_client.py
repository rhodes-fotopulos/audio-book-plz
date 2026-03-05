"""Ollama LLM client wrapper for structured output.

Provides a single entry point for all LLM calls in the attribution pipeline:
- Intelligent model selection (14B preferred, 8B fallback based on available RAM)
- Model lifecycle management (preload with keep_alive=-1, explicit unload)
- Structured JSON output via Pydantic schema + Ollama format parameter
- Automatic retry logic (up to 3 attempts)
- Qwen3 /no_think mode for faster structured responses
- Token estimation for context window budgeting

All LLM calls in the attribution package go through call_llm_structured().

Note: For 14B on 16GB machines, set OLLAMA_KV_CACHE_TYPE=q8_0 environment
variable to halve KV cache memory usage with minimal quality impact.
"""

from __future__ import annotations

import logging
from typing import TypeVar

import psutil
from ollama import chat as ollama_chat
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MODEL_14B = "qwen3.5:9b"
"""Ollama model name for Qwen3.5 9B (preferred)."""

MODEL_8B = "qwen3.5:4b"
"""Ollama model name for Qwen3.5 4B (fallback)."""

DEFAULT_MODEL = MODEL_14B
"""Default model to attempt when no override is specified."""

RAM_THRESHOLD_GB = 12.0
"""Minimum available RAM (GB) to use 14B model.

14B Q4_K_M weights ~10GB + KV cache q8_0 ~2GB = ~12GB.
Below this threshold, fall back to 8B to avoid swap thrashing.
"""

CONTEXT_WINDOW = 32768
"""Explicit num_ctx -- Ollama defaults to 2048 without this."""

MAX_RESPONSE_TOKENS = 4096
"""Maximum tokens for LLM response (num_predict)."""

MAX_RETRIES = 3
"""Retry count for failed LLM calls."""

NOTHINK_SUFFIX = " /no_think"
"""Appended to system prompts to disable Qwen3 thinking mode."""

T = TypeVar("T", bound=BaseModel)

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

_active_model: str | None = None
"""Currently loaded/selected model. Set by select_model() or preload_model()."""


# ---------------------------------------------------------------------------
# Model selection and lifecycle
# ---------------------------------------------------------------------------


def select_model(override: str | None = None) -> str:
    """Select the best LLM model based on available RAM or user override.

    Args:
        override: If not None, use this model name directly (user forced).

    Returns:
        Model name string for Ollama (e.g., "qwen3:14b" or "qwen3:8b").
    """
    global _active_model

    if override is not None:
        _active_model = override
        logger.info("Model override: %s", override)
        return override

    total_gb = psutil.virtual_memory().total / (1024 ** 3)

    if total_gb >= RAM_THRESHOLD_GB:
        _active_model = MODEL_14B
        logger.info(
            "Total RAM %.1f GB >= %.1f GB threshold -- using %s",
            total_gb,
            RAM_THRESHOLD_GB,
            MODEL_14B,
        )
        return MODEL_14B
    else:
        _active_model = MODEL_8B
        logger.warning(
            "Total RAM %.1f GB below %.1f GB threshold -- "
            "falling back to %s (attribution quality may be reduced)",
            total_gb,
            RAM_THRESHOLD_GB,
            MODEL_8B,
        )
        return MODEL_8B


def preload_model(model: str | None = None) -> str:
    """Preload model into Ollama with infinite keep_alive.

    Sends an empty request with keep_alive=-1 to load the model into
    memory and keep it resident until explicit unload. This avoids
    the 5-minute default timeout between LLM phases.

    Args:
        model: Model name to preload. If None, auto-selects via select_model().

    Returns:
        The model name that was preloaded.
    """
    global _active_model

    if model is None:
        model = select_model()

    try:
        ollama_chat(
            model=model,
            messages=[],
            keep_alive=-1,
        )
        _active_model = model
        logger.info(
            "Model %s preloaded with keep_alive=-1 (resident until explicit unload)",
            model,
        )
    except Exception as e:
        logger.warning("Could not preload model %s: %s", model, e)
        _active_model = model  # Still set as active even if preload fails

    return model


def get_active_model() -> str:
    """Return the currently active model, selecting one if needed.

    Returns:
        Model name string. Uses cached _active_model if set,
        otherwise calls select_model() to choose based on RAM.
    """
    global _active_model

    if _active_model is not None:
        return _active_model

    return select_model()


# ---------------------------------------------------------------------------
# Core LLM call
# ---------------------------------------------------------------------------


def call_llm_structured(
    system_prompt: str,
    user_content: str,
    schema_class: type[T],
    num_ctx: int = CONTEXT_WINDOW,
) -> T | None:
    """Call Ollama with structured output and retry logic.

    Sends a chat request to the active Qwen3 model with the Pydantic
    model's JSON schema as the format constraint. Ollama uses
    grammar-constrained decoding to guarantee valid JSON output
    matching the schema.

    Args:
        system_prompt: System message for the LLM (gets /no_think appended).
        user_content: User message containing the text to process.
        schema_class: Pydantic model class for response validation.
        num_ctx: Context window size (default: 32768).

    Returns:
        Validated Pydantic model instance, or None if all retries fail.
    """
    model = get_active_model()
    full_system_prompt = system_prompt + NOTHINK_SUFFIX

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = ollama_chat(
                model=model,
                messages=[
                    {"role": "system", "content": full_system_prompt},
                    {"role": "user", "content": user_content},
                ],
                format=schema_class.model_json_schema(),
                options={
                    "temperature": 0,
                    "num_ctx": num_ctx,
                    "num_predict": MAX_RESPONSE_TOKENS,
                },
                keep_alive=-1,
            )
            result = schema_class.model_validate_json(response.message.content)
            return result
        except ValidationError as e:
            logger.warning(
                "Attempt %d/%d: validation error: %s", attempt, MAX_RETRIES, e
            )
        except Exception as e:
            logger.warning(
                "Attempt %d/%d: LLM error: %s", attempt, MAX_RETRIES, e
            )

    logger.error("All %d attempts failed for schema %s", MAX_RETRIES, schema_class.__name__)
    return None


# ---------------------------------------------------------------------------
# Model management
# ---------------------------------------------------------------------------


def unload_model(model: str | None = None) -> None:
    """Explicitly unload model from Ollama to free memory.

    Sends a request with keep_alive=0 to immediately evict the model
    from GPU/RAM. Important at phase boundaries so Ollama releases
    memory before TTS engines load.

    Args:
        model: Model name to unload. If None, unloads the active model
            or DEFAULT_MODEL as fallback.
    """
    global _active_model

    if model is None:
        model = _active_model or DEFAULT_MODEL

    try:
        ollama_chat(
            model=model,
            messages=[],
            keep_alive=0,
        )
        logger.info("Model %s unloaded from Ollama", model)
    except Exception as e:
        logger.debug("Could not unload model %s: %s", model, e)

    _active_model = None


# ---------------------------------------------------------------------------
# Token estimation
# ---------------------------------------------------------------------------


def estimate_tokens(text: str) -> int:
    """Estimate token count using conservative 1:4 char-to-token ratio.

    English text averages roughly 4 characters per token. This is a
    conservative estimate (actual ratio is often higher, meaning fewer
    tokens), so it errs on the side of leaving more room in the context
    window.

    Args:
        text: Text to estimate tokens for.

    Returns:
        Estimated token count (integer, always >= 0).
    """
    return max(0, len(text) // 4)
