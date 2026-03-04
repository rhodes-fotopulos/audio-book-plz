"""Content-hash-keyed JSON file cache for attribution results.

Enables incremental re-runs (ATTR-06): chapters whose content hasn't
changed are skipped on subsequent runs, avoiding redundant LLM calls.

Cache keys are SHA-256 hashes of "{pass_name}:{content}" to differentiate
extraction and attribution results for the same chapter text.

Cache files are human-readable JSON (indent=2) stored in the book's
output directory under .cache/.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def get_cache_key(content: str, pass_name: str) -> str:
    """Compute a SHA-256 cache key for content and pass combination.

    Args:
        content: The text content to hash (e.g., chapter text).
        pass_name: Pass identifier ("extraction" or "attribution")
                   to differentiate cache entries for the same text.

    Returns:
        Hex digest string suitable as a filename.
    """
    composite = f"{pass_name}:{content}"
    return hashlib.sha256(composite.encode()).hexdigest()


def check_cache(cache_dir: Path, key: str) -> dict | None:
    """Check if a cached result exists for the given key.

    Args:
        cache_dir: Directory containing cache JSON files.
        key: SHA-256 hex digest from get_cache_key().

    Returns:
        Parsed JSON dict if cache hit, None if cache miss.
    """
    cache_file = cache_dir / f"{key}.json"
    if cache_file.exists():
        try:
            return json.loads(cache_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Cache read error for %s: %s", key[:12], e)
            return None
    return None


def write_cache(cache_dir: Path, key: str, data: dict) -> None:
    """Write a result to the cache with atomic write pattern.

    Uses write-to-tmp-then-rename to prevent corruption if the process
    is interrupted mid-write (e.g., keyboard interrupt during overnight run).

    Args:
        cache_dir: Directory to store cache JSON files.
        key: SHA-256 hex digest from get_cache_key().
        data: Result data to cache (must be JSON-serializable).
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{key}.json"
    tmp_file = cache_dir / f"{key}.json.tmp"

    try:
        tmp_file.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        tmp_file.rename(cache_file)
    except OSError as e:
        logger.warning("Cache write error for %s: %s", key[:12], e)
        # Clean up tmp file if rename failed
        tmp_file.unlink(missing_ok=True)


def clear_cache(cache_dir: Path) -> int:
    """Remove all cached results from the cache directory.

    Used when the user wants a completely fresh re-run.

    Args:
        cache_dir: Directory containing cache JSON files.

    Returns:
        Number of cache files removed.
    """
    if not cache_dir.exists():
        return 0

    count = 0
    for cache_file in cache_dir.glob("*.json"):
        try:
            cache_file.unlink()
            count += 1
        except OSError as e:
            logger.warning("Could not remove cache file %s: %s", cache_file.name, e)

    return count
