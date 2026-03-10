"""XHTML to plain text block extraction for EPUB chapters."""

import re

from ebooklib import epub
from bs4 import BeautifulSoup


# Block-level tags to extract from chapter XHTML
_BLOCK_TAGS = ["p", "div", "h1", "h2", "h3", "h4", "hr", "blockquote"]

# Patterns for detecting table-of-contents text content
_TOC_HEADING_RE = re.compile(
    r'^table\s+of\s+contents$',
    re.IGNORECASE,
)

# A block that is just "Chapter N" repeated (TOC entries)
_TOC_ENTRY_RE = re.compile(
    r'^(?:chapter\s+\d+\s*)+$',
    re.IGNORECASE,
)

# A block that is predominantly bare numbers (page numbers / chapter numbers from TOC)
_BARE_NUMBERS_RE = re.compile(
    r'^(?:\d+\s+)*(?:chapter\s+\d+\s*)*(?:\d+\s*)*$',
    re.IGNORECASE,
)


def _is_toc_content(text: str) -> bool:
    """Return True if text looks like table-of-contents content."""
    stripped = text.strip()
    if _TOC_HEADING_RE.match(stripped):
        return True
    if _TOC_ENTRY_RE.match(stripped):
        return True
    # Bare numbers mixed with "Chapter N" — e.g. "15 Chapter 16 Chapter 17"
    if _BARE_NUMBERS_RE.match(stripped) and len(stripped) > 10:
        return True
    # "Table of Contents Chapter 1 Chapter 2 ..." — TOC heading + entries in one block
    if _TOC_HEADING_RE.match(stripped.split("Chapter")[0].strip()):
        return True
    return False


def chapter_to_text_blocks(
    item: epub.EpubHtml,
) -> list[tuple[str, str, dict]]:
    """Extract text blocks from an EPUB chapter in reading order.

    Parses the chapter's body content with lxml (faster and more tolerant of
    malformed XHTML than html.parser). Iterates block-level tags only —
    avoids nav/head/script content (per research Pitfall 5).

    Filters out table-of-contents content (nav elements, TOC headings,
    and blocks consisting of "Chapter N" entries).

    CSS class attributes are preserved in the returned dict so that callers
    can detect scene break classes like "break", "separator", or "divider"
    (per research Pitfall 7) before stripping HTML.

    Args:
        item: An EpubHtml spine item from ebooklib.

    Returns:
        A list of (tag_name, text, attrs) tuples where:
        - tag_name: lowercase HTML tag name e.g. 'p', 'h1', 'hr'
        - text: plain text extracted from the tag (empty string for <hr>)
        - attrs: dict with 'class' key containing a list of CSS class names
    """
    content = item.get_body_content()
    if not content:
        return []

    soup = BeautifulSoup(content, "lxml")

    # Remove <nav> elements entirely (EPUB3 TOC nav)
    for nav in soup.find_all("nav"):
        nav.decompose()

    # Remove elements with TOC-related roles or types
    for el in soup.find_all(attrs={"epub:type": "toc"}):
        el.decompose()
    for el in soup.find_all(attrs={"role": "doc-toc"}):
        el.decompose()

    blocks: list[tuple[str, str, dict]] = []

    for tag in soup.find_all(_BLOCK_TAGS):
        tag_name = tag.name
        attrs = {"class": tag.get("class", [])}

        if tag_name == "hr":
            # Scene break indicator — no text content
            blocks.append(("hr", "", attrs))
            continue

        text = tag.get_text(separator=" ", strip=True)
        if not text:
            continue

        # Skip table-of-contents content
        if _is_toc_content(text):
            continue

        blocks.append((tag_name, text, attrs))

    return blocks
