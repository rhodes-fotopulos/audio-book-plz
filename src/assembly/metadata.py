"""EPUB metadata extraction for ID3 tagging.

Extracts title, author, and cover image from EPUB files using ebooklib.
Cover extraction tries the OPF metadata method first, then falls back to
scanning IMAGE items for filenames containing 'cover'.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import ebooklib
from ebooklib import epub

from src.assembly.models import EpubMetadata

# Accepted cover image MIME types
_VALID_COVER_MIMES = {"image/jpeg", "image/png", "image/gif"}


def extract_epub_metadata(epub_path: Path) -> EpubMetadata:
    """Extract title, author, and cover image from an EPUB file.

    Uses Dublin Core metadata for title and author.  Cover image extraction
    first tries the OPF ``<meta name="cover">`` element, then falls back to
    scanning all IMAGE items for filenames containing 'cover'.

    Args:
        epub_path: Path to the EPUB file.

    Returns:
        EpubMetadata with extracted values.  cover_data and cover_mime are
        None if no valid cover image is found.
    """
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=UserWarning, module="ebooklib")
        book = epub.read_epub(str(epub_path), options={"ignore_ncx": True})

    # --- Title ---
    title_meta = book.get_metadata("DC", "title")
    title = title_meta[0][0] if title_meta else "Unknown Title"

    # --- Author ---
    creator_meta = book.get_metadata("DC", "creator")
    author = creator_meta[0][0] if creator_meta else "Unknown Author"

    # --- Cover image ---
    cover_data, cover_mime = _extract_cover(book)

    return EpubMetadata(
        title=title,
        author=author,
        cover_data=cover_data,
        cover_mime=cover_mime,
    )


def _extract_cover(book: epub.EpubBook) -> tuple[bytes | None, str | None]:
    """Extract cover image bytes and MIME type from an EPUB.

    Strategy:
    1. OPF metadata: ``<meta name="cover" content="cover-id">``
    2. Filename scan: IMAGE items with 'cover' in the filename.

    Returns:
        Tuple of (image_bytes, mime_type) or (None, None).
    """
    # Method 1: OPF cover metadata
    cover_meta = book.get_metadata("OPF", "cover")
    if cover_meta:
        # cover_meta is a list of tuples: [('', {'name': 'cover', 'content': 'cover-id'})]
        for _text, attrs in cover_meta:
            cover_id = attrs.get("content", "")
            if not cover_id:
                continue
            item = book.get_item_with_id(cover_id)
            if item is not None:
                mime = item.media_type
                if mime in _VALID_COVER_MIMES:
                    return item.get_content(), mime

    # Method 2: Scan IMAGE items for 'cover' in filename
    for item in book.get_items_of_type(ebooklib.ITEM_IMAGE):
        name = (item.get_name() or "").lower()
        if "cover" in name:
            mime = item.media_type
            if mime in _VALID_COVER_MIMES:
                return item.get_content(), mime

    return None, None
