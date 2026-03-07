"""Ollama LLM client wrapper for structured output.

Provides a single entry point for all LLM calls in the attribution pipeline:
- Intelligent model selection (14B preferred, 8B fallback based on available RAM)
- Model lifecycle management (preload with keep_alive=-1, explicit unload)
- Structured JSON output via Pydantic schema + Ollama format parameter
- Automatic retry logic (up to 3 attempts)
- Qwen3 think=False mode for faster structured responses
- Token estimation for context window budgeting

All LLM calls in the attribution package go through call_llm_structured().

Note: For 14B on 16GB machines, set OLLAMA_KV_CACHE_TYPE=q8_0 environment
variable to halve KV cache memory usage with minimal quality impact.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
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

MAX_RESPONSE_TOKENS = 16384
"""Maximum tokens for LLM response (num_predict). Caps output to prevent
the model from generating until it fills the entire context window."""

MAX_RETRIES = 3
"""Retry count for failed LLM calls."""

CLAUDE_CODE_MODEL = "claude-code"
"""Model name that triggers Claude Code CLI backend."""

_CLAUDE_CODE_PREFIX = "claude-code"
"""Prefix for detecting Claude Code model variants."""

CLAUDE_CODE_MAX_WORKERS = 32
"""Max concurrent claude CLI subprocesses. API-bound, not GPU-bound."""


T = TypeVar("T", bound=BaseModel)

_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?\s*```$", re.DOTALL)


def _deref_schema(schema: dict) -> dict:
    """Inline all $ref references in a JSON schema.

    Small models struggle with $ref pointers. This resolves them
    so enum values and object properties are visible inline.
    """
    defs = schema.pop("$defs", {})
    if not defs:
        return schema

    def _resolve(node):
        if isinstance(node, dict):
            if "$ref" in node:
                ref_path = node["$ref"]  # e.g. "#/$defs/EmotionCategory"
                ref_name = ref_path.rsplit("/", 1)[-1]
                if ref_name in defs:
                    return _resolve(defs[ref_name])
                return node
            return {k: _resolve(v) for k, v in node.items()}
        if isinstance(node, list):
            return [_resolve(item) for item in node]
        return node

    return _resolve(schema)


class TruncationError(Exception):
    """Raised when LLM output is truncated (hit token/context limit).

    Callers should handle this by splitting input into smaller chunks
    rather than retrying with the same input.
    """


def _strip_fences(text: str) -> str:
    """Strip markdown code fences if present (e.g. ```json ... ```)."""
    m = _FENCE_RE.match(text.strip())
    return m.group(1) if m else text

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
        if override.startswith(_CLAUDE_CODE_PREFIX):
            logger.info("Model override: %s (Claude Code CLI)", override)
            return override
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

    if model.startswith(_CLAUDE_CODE_PREFIX):
        _active_model = model
        logger.info("Claude Code CLI — no preload needed")
        return model

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


def get_max_workers() -> int:
    """Return max parallel workers for the active model.

    Ollama uses 1 (GPU-bound). Claude Code uses CLAUDE_CODE_MAX_WORKERS
    since calls are API-bound and can run concurrently.
    """
    model = get_active_model()
    if model.startswith(_CLAUDE_CODE_PREFIX):
        return CLAUDE_CODE_MAX_WORKERS
    return 1


# ---------------------------------------------------------------------------
# Claude Code CLI backend
# ---------------------------------------------------------------------------


def _log_claude_error(
    attempt: int,
    message: str,
    stderr: str | None,
    stdout: str | None,
    schema_name: str,
) -> None:
    """Print Claude Code CLI errors to console (logging has no handler)."""
    parts = [f"Attempt {attempt}/{MAX_RETRIES} [{schema_name}]: {message}"]
    if stderr:
        parts.append(f"  stderr: {stderr[:500]}")
    if stdout:
        parts.append(f"  stdout: {stdout[:500]}")
    print("\n".join(parts))


def _call_claude_code_structured(
    system_prompt: str,
    user_content: str,
    schema_class: type[T],
) -> T | None:
    """Call Claude Code CLI with structured output and retry logic.

    Shells out to `claude -p` with `--json-schema` for grammar-constrained
    JSON output. Runs through the user's Claude Max subscription (no API key).

    Args:
        system_prompt: System message for the LLM.
        user_content: User message (piped via stdin to avoid arg length limits).
        schema_class: Pydantic model class for response validation.

    Returns:
        Validated Pydantic model instance, or None if all retries fail.
    """
    schema = json.dumps(schema_class.model_json_schema())

    cmd = [
        "claude", "-p",
        "--output-format", "json",
        "--json-schema", schema,
        "--system-prompt", system_prompt,
        "--tools", "",
        "--no-session-persistence",
        "--model", "sonnet",
    ]

    # Clear CLAUDECODE env var to allow nested CLI invocation
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

    if os.environ.get("CLAUDECODE"):
        logger.warning(
            "CLAUDECODE env var detected — running claude CLI from inside "
            "Claude Code may fail. Consider running from a regular terminal."
        )

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            proc = subprocess.run(
                cmd,
                input=user_content,
                capture_output=True,
                text=True,
                timeout=300,
                env=env,
            )
            if proc.returncode != 0:
                _log_claude_error(
                    attempt, f"CLI error (rc={proc.returncode})",
                    proc.stderr, proc.stdout, schema_class.__name__,
                )
                continue

            if not proc.stdout or not proc.stdout.strip():
                _log_claude_error(
                    attempt, "CLI returned empty output",
                    proc.stderr, None, schema_class.__name__,
                )
                continue

            # --output-format json returns structured_output alongside result text
            wrapper = json.loads(proc.stdout)
            raw_result = wrapper.get("structured_output")
            if raw_result is None:
                # Fall back to result field if structured_output missing
                raw_result = wrapper.get("result", proc.stdout)

            if raw_result is None:
                _log_claude_error(
                    attempt, "No structured_output or result in response",
                    None, proc.stdout, schema_class.__name__,
                )
                continue

            # Handle case where result is already a dict (parsed JSON)
            if isinstance(raw_result, dict):
                result = schema_class.model_validate(raw_result)
            else:
                raw_result = _strip_fences(str(raw_result))
                result = schema_class.model_validate_json(raw_result)

            return result
        except ValidationError as e:
            _log_claude_error(
                attempt, f"Validation error: {e}",
                None, proc.stdout, schema_class.__name__,
            )
        except subprocess.TimeoutExpired:
            _log_claude_error(
                attempt, "CLI timed out (300s)",
                None, None, schema_class.__name__,
            )
        except Exception as e:
            _log_claude_error(
                attempt, f"Error: {e}",
                None, None, schema_class.__name__,
            )

    print(
        f"[claude-code] All {MAX_RETRIES} attempts failed "
        f"for {schema_class.__name__}"
    )
    return None


# ---------------------------------------------------------------------------
# Core LLM call
# ---------------------------------------------------------------------------


def _try_validate(raw: str, schema_class: type[T]) -> T:
    """Try to validate JSON against schema, handling bare arrays.

    When the schema expects an object with a single list field (e.g.,
    ``{"characters": [...]}``) but the LLM returns a bare JSON array,
    this wraps the array in the expected object structure.

    Args:
        raw: Raw JSON string from the LLM.
        schema_class: Pydantic model class for validation.

    Returns:
        Validated Pydantic model instance.

    Raises:
        ValidationError: If the JSON doesn't match the schema.
    """
    try:
        return schema_class.model_validate_json(raw)
    except ValidationError:
        # If schema has a single list field and response is a bare array,
        # wrap it automatically
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            raise  # Let caller handle malformed JSON (e.g. truncation)
        if isinstance(parsed, list):
            fields = schema_class.model_fields
            list_fields = [
                name for name, field in fields.items()
                if hasattr(field.annotation, "__origin__")
                and field.annotation.__origin__ is list
            ]
            if len(list_fields) == 1:
                return schema_class.model_validate({list_fields[0]: parsed})
        raise


def call_llm_structured(
    system_prompt: str,
    user_content: str,
    schema_class: type[T],
    num_ctx: int = CONTEXT_WINDOW,
) -> T | None:
    """Call Ollama with structured output and retry logic.

    Uses think=False with the JSON schema embedded in the system prompt.
    Does NOT use Ollama's ``format="json"`` grammar constraint, which
    causes hangs on larger inputs with Qwen3.5 models.

    Args:
        system_prompt: System message for the LLM.
        user_content: User message containing the text to process.
        schema_class: Pydantic model class for response validation.
        num_ctx: Context window size (default: 32768).

    Returns:
        Validated Pydantic model instance, or None if all retries fail.
    """
    model = get_active_model()

    # Dispatch to Claude Code CLI backend
    if model.startswith(_CLAUDE_CODE_PREFIX):
        return _call_claude_code_structured(system_prompt, user_content, schema_class)

    schema_json = json.dumps(
        _deref_schema(schema_class.model_json_schema()), indent=2
    )
    full_system_prompt = (
        f"{system_prompt}\n\n"
        f"Return valid JSON matching this schema:\n{schema_json}\n\n"
        f"Return ONLY valid JSON. No other text, no markdown, no explanation."
    )

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = ollama_chat(
                model=model,
                messages=[
                    {"role": "system", "content": full_system_prompt},
                    {"role": "user", "content": user_content},
                ],
                think=False,
                options={
                    "temperature": 0,
                    "num_ctx": num_ctx,
                    "num_predict": MAX_RESPONSE_TOKENS,
                },
                keep_alive=-1,
            )
            raw = _strip_fences(response.message.content)
            result = _try_validate(raw, schema_class)
            return result
        except ValidationError as e:
            error_str = str(e)
            if "EOF" in error_str or "Unterminated string" in error_str:
                print("Output truncated (hit context limit), retries won't help")
                raise TruncationError(error_str) from e
            print(
                f"Attempt {attempt}/{MAX_RETRIES}: validation error: {e}"
            )
        except json.JSONDecodeError as e:
            error_str = str(e)
            if "Unterminated string" in error_str or "Expecting" in error_str:
                print("Output truncated (malformed JSON), retries won't help")
                raise TruncationError(error_str) from e
            print(
                f"Attempt {attempt}/{MAX_RETRIES}: JSON parse error: {e}"
            )
        except Exception as e:
            print(
                f"Attempt {attempt}/{MAX_RETRIES}: LLM error: {e}"
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

    if model.startswith(_CLAUDE_CODE_PREFIX):
        logger.info("Claude Code CLI — no unload needed")
        _active_model = None
        return

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
