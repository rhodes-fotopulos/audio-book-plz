"""Ollama LLM client wrapper for structured output.

Provides a single entry point for all LLM calls in Phase 2:
- Structured JSON output via Pydantic schema + Ollama format parameter
- Automatic retry logic (up to 3 attempts)
- Qwen3 /no_think mode for faster structured responses
- Model unloading for memory management
- Token estimation for context window budgeting

All LLM calls in the attribution package go through call_llm_structured().
"""

from __future__ import annotations

import logging
from typing import TypeVar

from ollama import chat as ollama_chat
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MODEL = "qwen3:8b"
"""Ollama model name for Qwen3 8B."""

CONTEXT_WINDOW = 32768
"""Explicit num_ctx — Ollama defaults to 2048 without this."""

MAX_RESPONSE_TOKENS = 4096
"""Maximum tokens for LLM response (num_predict)."""

MAX_RETRIES = 3
"""Retry count for failed LLM calls."""

NOTHINK_SUFFIX = " /no_think"
"""Appended to system prompts to disable Qwen3 thinking mode."""

T = TypeVar("T", bound=BaseModel)

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

    Sends a chat request to Qwen3 8B with the Pydantic model's JSON schema
    as the format constraint. Ollama uses grammar-constrained decoding to
    guarantee valid JSON output matching the schema.

    Args:
        system_prompt: System message for the LLM (gets /no_think appended).
        user_content: User message containing the text to process.
        schema_class: Pydantic model class for response validation.
        num_ctx: Context window size (default: 32768).

    Returns:
        Validated Pydantic model instance, or None if all retries fail.
    """
    full_system_prompt = system_prompt + NOTHINK_SUFFIX

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = ollama_chat(
                model=MODEL,
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


def unload_model(model: str = MODEL) -> None:
    """Explicitly unload model from Ollama to free memory.

    Sends a request with keep_alive=0 to immediately evict the model
    from GPU/RAM. Important at the Phase 2/3 boundary so Ollama releases
    memory before Chatterbox TTS loads in Phase 4.

    Silently handles connection errors (Ollama might not be running).
    """
    try:
        ollama_chat(
            model=model,
            messages=[],
            keep_alive=0,
        )
        logger.info("Model %s unloaded from Ollama", model)
    except Exception as e:
        logger.debug("Could not unload model %s: %s", model, e)


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
