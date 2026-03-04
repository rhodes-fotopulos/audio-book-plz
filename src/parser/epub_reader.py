"""EPUB loading, spine-order iteration, and front/back matter detection."""

import re
import warnings

import ebooklib
from bs4 import BeautifulSoup
from ebooklib import epub


# Back matter headings to exclude (non-story endings)
_BACK_MATTER_EXCLUDE = re.compile(
    r'\b(acknowledgment|acknowledgement|about\s+the\s+author|author\s+bio|'
    r'reading\s+guide|also\s+by|excerpt|preview|note\s+from\s+the\s+author|'
    r'discussion\s+questions)\b',
    re.IGNORECASE,
)

# Story endings to KEEP (epilogues, afterwords, etc.)
_BACK_MATTER_INCLUDE = re.compile(
    r'\b(epilogue|afterword|coda|postscript)\b',
    re.IGNORECASE,
)

# Chapter/part heading patterns for front matter detection (Tier 2)
_CHAPTER_PATTERN = re.compile(
    r'\b(chapter|part|prologue)\b',
    re.IGNORECASE,
)

_STANDALONE_NUMBER = re.compile(
    r'^(?:\d+|[ivxlcdmIVXLCDM]+|one|two|three|four|five|six|seven|eight|nine|ten)'
    r'(?:\s+[-–—:]\s+.+)?$',
    re.IGNORECASE,
)


def load_epub(path: str) -> epub.EpubBook:
    """Load an EPUB file with warning suppression.

    Suppresses ebooklib's UserWarning about ignore_ncx and forces EPUB3 nav
    document usage (per research Pattern 7 and Pitfalls 2/4).

    Args:
        path: Filesystem path to the EPUB file.

    Returns:
        Loaded EpubBook instance.
    """
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=UserWarning, module="ebooklib")
        return epub.read_epub(path, options={"ignore_ncx": True})


def get_story_chapters(book: epub.EpubBook) -> list[epub.EpubHtml]:
    """Return story chapters in spine (reading) order with front/back matter excluded.

    Uses hybrid front matter detection:
    - Tier 1: EPUB guide element (type='text' or 'bodymatter')
    - Tier 2: First <h1>/<h2> containing chapter-like text
    - Tier 3: Include everything (prefer inclusion over exclusion)

    Back matter exclusion: removes acknowledgments, author bios, reading
    guides, and excerpts while keeping epilogues and afterwords.

    Args:
        book: Loaded EpubBook from load_epub().

    Returns:
        List of EpubHtml items representing story chapters in reading order.
    """
    # Step 1: Collect all linear spine items in order
    all_docs: list[epub.EpubHtml] = []
    for item_id, linear in book.spine:
        item = book.get_item_with_id(item_id)
        if item is None:
            continue
        if item.get_type() != ebooklib.ITEM_DOCUMENT:
            continue
        # Skip non-linear items: covers, footnotes, endnotes
        if linear == "no":
            continue
        all_docs.append(item)

    if not all_docs:
        return []

    # Step 2: Find story start index (front matter detection)
    story_start = _find_story_start(book, all_docs)

    # Step 3: Find story end index (back matter detection)
    story_end = _find_story_end(all_docs, story_start)

    return all_docs[story_start:story_end]


def _find_story_start(book: epub.EpubBook, chapters: list[epub.EpubHtml]) -> int:
    """Return index of first chapter to include. 0 = include all.

    Tier 1: EPUB guide element with type 'text' or 'bodymatter'.
    Tier 2: First <h1>/<h2> containing chapter/part/prologue or a number.
    Tier 3: Return 0 (include everything).
    """
    # Tier 1: Check EPUB guide element
    if hasattr(book, "guide") and book.guide:
        for guide_ref in book.guide:
            ref_type = guide_ref.get("type", "").lower()
            if ref_type in ("text", "bodymatter"):
                href = guide_ref.get("href", "").split("#")[0]
                for i, ch in enumerate(chapters):
                    name = ch.get_name()
                    if name.endswith(href) or href.endswith(name) or href == name:
                        return i

    # Tier 2: Heading scan
    for i, ch in enumerate(chapters):
        content = ch.get_body_content()
        if not content:
            continue
        soup = BeautifulSoup(content, "lxml")
        for tag in soup.find_all(["h1", "h2"]):
            text = tag.get_text(strip=True)
            if _CHAPTER_PATTERN.search(text) or _STANDALONE_NUMBER.match(text):
                return i

    # Tier 3: Include everything (user preference: inclusion over exclusion)
    return 0


def _find_story_end(chapters: list[epub.EpubHtml], story_start: int) -> int:
    """Return exclusive end index for story chapters.

    Scans from the end backwards to exclude non-story back matter such as
    acknowledgments, author bios, and reading guides. Epilogues, afterwords,
    codas, and postscripts are kept.

    Args:
        chapters: Full list of all chapters.
        story_start: Index where the story begins (from _find_story_start).

    Returns:
        Exclusive end index (use as chapters[story_start:story_end]).
    """
    story_end = len(chapters)

    for i in range(len(chapters) - 1, story_start - 1, -1):
        ch = chapters[i]
        content = ch.get_body_content()
        if not content:
            story_end = i
            continue

        soup = BeautifulSoup(content, "lxml")
        headings = soup.find_all(["h1", "h2", "h3"])
        if not headings:
            break

        heading_text = " ".join(h.get_text(strip=True) for h in headings)

        # Explicit story endings: keep these and stop scanning back
        if _BACK_MATTER_INCLUDE.search(heading_text):
            break

        # Non-story back matter: exclude and continue scanning back
        if _BACK_MATTER_EXCLUDE.search(heading_text):
            story_end = i
            continue

        # Unrecognised chapter: this is story content — stop scanning
        break

    return story_end
