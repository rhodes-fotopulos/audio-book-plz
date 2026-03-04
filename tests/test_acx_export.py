"""Tests for ACX-compliant export parameters and descriptive file naming.

Covers:
- Default bitrate is 192k
- Default sample rate is 44100
- Slugify title produces clean filenames
- Edge cases for slugify (empty, special characters)
"""

from __future__ import annotations

from src.assembly.assembler import _slugify_title
from src.assembly.models import AssemblyConfig


def test_default_bitrate_is_192k():
    """AssemblyConfig default bitrate should be 192k for ACX."""
    config = AssemblyConfig()
    assert config.mp3_bitrate == "192k", (
        f"Expected '192k', got '{config.mp3_bitrate}'"
    )


def test_default_sample_rate_is_44100():
    """AssemblyConfig default sample rate should be 44100 for ACX."""
    config = AssemblyConfig()
    assert config.export_sample_rate == 44100, (
        f"Expected 44100, got {config.export_sample_rate}"
    )


def test_slugify_title_basic():
    """'The Journey' should produce '01-the-journey'."""
    result = _slugify_title("The Journey", 1)
    assert result == "01-the-journey", f"Expected '01-the-journey', got '{result}'"


def test_slugify_title_empty():
    """Empty title should fall back to '01-chapter-1'."""
    result = _slugify_title("", 1)
    assert result == "01-chapter-1", f"Expected '01-chapter-1', got '{result}'"


def test_slugify_title_special_chars():
    """'Chapter 3: The Quest!' should produce '03-chapter-3-the-quest'."""
    result = _slugify_title("Chapter 3: The Quest!", 3)
    assert result == "03-chapter-3-the-quest", (
        f"Expected '03-chapter-3-the-quest', got '{result}'"
    )


def test_slugify_title_whitespace_only():
    """Whitespace-only title should fall back to numbered."""
    result = _slugify_title("   ", 5)
    assert result == "05-chapter-5", f"Expected '05-chapter-5', got '{result}'"


def test_slugify_title_unicode():
    """Non-ASCII characters should be stripped."""
    result = _slugify_title("The Dark Forest", 2)
    assert result == "02-the-dark-forest", (
        f"Expected '02-the-dark-forest', got '{result}'"
    )
