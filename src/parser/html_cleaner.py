"""XHTML to plain text block extraction for EPUB chapters."""

from ebooklib import epub
from bs4 import BeautifulSoup


# Block-level tags to extract from chapter XHTML
_BLOCK_TAGS = ["p", "div", "h1", "h2", "h3", "h4", "hr", "blockquote"]


def chapter_to_text_blocks(
    item: epub.EpubHtml,
) -> list[tuple[str, str, dict]]:
    """Extract text blocks from an EPUB chapter in reading order.

    Parses the chapter's body content with lxml (faster and more tolerant of
    malformed XHTML than html.parser). Iterates block-level tags only —
    avoids nav/head/script content (per research Pitfall 5).

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
    blocks: list[tuple[str, str, dict]] = []

    for tag in soup.find_all(_BLOCK_TAGS):
        tag_name = tag.name
        attrs = {"class": tag.get("class", [])}

        if tag_name == "hr":
            # Scene break indicator — no text content
            blocks.append(("hr", "", attrs))
            continue

        text = tag.get_text(separator=" ", strip=True)
        if text:
            blocks.append((tag_name, text, attrs))

    return blocks
