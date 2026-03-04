# Phase 1: EPUB Parsing and CLI Skeleton - Research

**Researched:** 2026-03-03
**Domain:** EPUB parsing, text segmentation, CLI framework
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Segment splitting logic:**
- Split text at sentence boundaries — each sentence becomes its own segment
- If a single sentence exceeds the character limit, force-split at the nearest clause boundary (comma, semicolon, em-dash)
- Dialogue lines from one speaker are kept as a single segment when they fit within the limit; split only when they exceed it
- The 280-character limit is a soft target — Claude has discretion on the exact ceiling based on what Chatterbox handles best

**Front and back matter boundaries:**
- Exclude everything before Chapter 1 (title pages, copyright, ToC, dedications, prefaces)
- Include epilogues and afterwords (story-related endings) but exclude acknowledgments, author bios, reading guides, and excerpts from other books
- Chapter detection approach is Claude's discretion — pick the most robust method based on research
- When the parser can't confidently identify where the story starts (unusual EPUB structure), include everything rather than risk missing story content

**Special content types:**
- Poetry, song lyrics, and verse embedded in the novel: tag as narration — narrator reads them
- Letters, notes, and text messages from characters: tag as dialogue by the sender, so Phase 2 can attribute them to the right character's voice
- Chapter epigraphs (quotes at start of chapters): include as narration
- Whether to add segment types beyond the four (narration, dialogue, chapter_heading, scene_break) is Claude's discretion — e.g., internal monologue type if research supports it

**Output structure and CLI feel:**
- All output goes in a dedicated `output/` directory inside the project, organized by book name
- CLI shows progress during parsing (chapters being processed) followed by a summary (chapter count, segment count, dialogue line count)
- Use Typer as the CLI framework (type-hint based, auto-generated help, colored output)
- `python main.py convert book.epub` runs all phases automatically in one shot — no confirmation prompt, suitable for overnight unattended runs

### Claude's Discretion

- Exact character limit ceiling (280 is soft target — optimize for Chatterbox)
- Chapter detection strategy (EPUB spine order vs heading-based vs hybrid)
- Whether to add additional segment types beyond the base four
- Exact output directory naming conventions within `output/`

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| PARSE-01 | User can parse an EPUB file (EPUB2 or EPUB3) and extract chapters in reading order | ebooklib 0.20 supports both; spine iteration is the correct reading-order API |
| PARSE-02 | Parser strips HTML tags and produces clean, speech-ready text per chapter | ebooklib `get_body_content()` + BeautifulSoup4 with lxml parser is the standard pattern |
| PARSE-03 | Parser splits text into segments tagged as narration, dialogue, chapter heading, or scene break | Regex-based dialogue detection + paragraph-type classification; see Architecture Patterns |
| PARSE-04 | Parser detects dialogue by identifying text within quotation marks (straight and curly variants) | Unicode regex covering `"`, `"`, `"`, `'`, `'` — well understood, no edge-case library needed |
| PARSE-05 | Parser filters out front matter, copyright pages, TOC, and dedication pages | EPUB guide element (`type=text`/`bodymatter`) + fallback heading scan; hybrid strategy documented below |
| PARSE-06 | Parser splits segments exceeding 280 characters at sentence boundaries for TTS compatibility | NLTK `sent_tokenize` + clause-boundary fallback; 280 chars confirmed safe ceiling for Chatterbox |
| PARSE-07 | Parser outputs ordered segments as JSON for downstream phases | Python `dataclasses` + `json.dump` via `dataclasses.asdict()` — no extra library needed |
| CLI-01 | User can run the full pipeline end-to-end with a single command | Typer 0.24.1 `app.command()` with `convert` command that chains phases internally |
| CLI-02 | User can run individual phases separately (parse, attribute, match, synthesize, assemble) | Typer multi-command pattern with `@app.command()` decorator on each phase function |
</phase_requirements>

---

## Summary

The standard Python EPUB-to-text stack is well-established and mature: **ebooklib** reads the EPUB container, **BeautifulSoup4 with lxml** converts XHTML chapters to clean text, and **NLTK's Punkt tokenizer** handles sentence boundary detection for TTS-safe splits. All three libraries are actively maintained, Python 3.11-compatible, and together cover every parsing requirement without hand-rolling complex logic. The main non-obvious trap is reading order: `get_items_of_type(ITEM_DOCUMENT)` returns manifest order, which is not spine order. Spine order is the authoritative reading sequence and must be used instead.

For the CLI, **Typer 0.24.1** with **Rich 14.3.3** (already a Typer dependency) is the correct choice matching the user's decision. Multi-command apps use `@app.command()` per function; Rich's `track()` provides per-chapter progress; `typer.secho()` / `rich.print()` covers colored output for summaries.

Front matter filtering is the most EPUB-ecosystem-specific problem. The EPUB guide element (EPUB2) and landmarks nav (EPUB3) provide a `type="text"` or `epub:type="bodymatter"` reference that identifies where the main story starts. Many commercially-published EPUBs include this. The robust strategy is a hybrid: check the guide/landmarks first, then fall back to the first document item whose HTML contains an `<h1>` or `<h2>` that looks like "Chapter", and finally fall back to include-everything. This matches the user's stated preference for inclusion over exclusion when uncertain.

**Primary recommendation:** Use `ebooklib` + `beautifulsoup4[lxml]` + `nltk` (punkt) for parsing; `Typer` + `Rich` (bundled) for CLI. Implement hybrid front matter detection. Keep segments at or below 280 characters (confirmed safe for Chatterbox's ~300-char hard limit with buffer for TTS stability).

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| ebooklib | 0.20 | Read EPUB2/EPUB3, access spine, manifest, guide, metadata | The only actively maintained Python EPUB read/write library; used by Booktype, Audiblez, ebook2audiobook |
| beautifulsoup4 | 4.14.3+ | Parse XHTML from EPUB chapters into clean text | Industry standard HTML/XML parsing; pairs with ebooklib in every EPUB-to-text project |
| lxml | 5.x | BS4 parser backend | Fastest and most reliable BS4 parser; recommended by BS4 docs over html.parser for EPUB content |
| nltk | 3.x | Sentence boundary detection (Punkt tokenizer) | Punkt handles literary prose, abbreviations (Dr., Mr., etc.), and ellipses correctly; lighter than spaCy for this single task |
| typer | 0.24.1 | CLI framework | User decision; type-hint-based, auto-generates help, zero boilerplate |
| rich | 14.3.3 | Progress bars and colored output | Already a Typer dependency (bundled); official Typer recommendation for terminal formatting |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| dataclasses (stdlib) | Python 3.11 | Segment data model and JSON serialization via `dataclasses.asdict()` | Sufficient for this phase's output; no external serialization library needed |
| json (stdlib) | Python 3.11 | Write `segments.json` | Direct use with `json.dump(dataclasses.asdict(obj), ...)` |
| re (stdlib) | Python 3.11 | Dialogue detection regex, scene break detection | Adequate for quotation mark detection; no NLP library needed for this task |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| lxml (BS4 backend) | html.parser | html.parser is stdlib (no install), but BS4 docs rank lxml fastest and most robust for XHTML; EPUB content is frequently malformed XML that lxml handles better |
| nltk (punkt) | spaCy | spaCy provides better NLP overall but is 400MB+ and requires a model download; punkt is 2MB and does exactly what's needed (sentence splitting) without language model overhead |
| nltk (punkt) | regex-based sentence split | Regex breaks on abbreviations (U.S., Dr., Mrs.) common in fiction; punkt is trained on prose and handles these correctly |
| dataclasses | pydantic | Pydantic adds validation and schema export (useful for later phases) but adds a dependency; stdlib dataclasses are sufficient for Phase 1's plain JSON output |
| Typer | Click | Typer is built on Click; user already decided Typer |
| Typer | argparse | Older, more verbose; user already decided Typer |

**Installation:**
```bash
pip install EbookLib beautifulsoup4 lxml nltk typer
# After install, run once to download punkt model:
python -c "import nltk; nltk.download('punkt_tab')"
```

---

## Architecture Patterns

### Recommended Project Structure

```
audio-book-plz/
├── main.py                  # Typer app entry point, all CLI commands
├── src/
│   ├── __init__.py
│   ├── parser/
│   │   ├── __init__.py
│   │   ├── epub_reader.py   # ebooklib wrapper: load, spine iteration, front matter detection
│   │   ├── html_cleaner.py  # BeautifulSoup: XHTML -> plain text, tag classification
│   │   ├── segmenter.py     # Sentence splitting, segment type tagging, character limit enforcement
│   │   └── models.py        # Segment dataclass, SegmentType enum, book metadata
│   └── pipeline.py          # Orchestrates phases 1-5 for `convert` command
├── output/
│   └── {book-slug}/
│       ├── segments.json    # Phase 1 output
│       └── ...              # Later phases write here
└── pyproject.toml
```

### Pattern 1: Spine-Order Chapter Iteration (CRITICAL)

**What:** Iterate EPUB items via `book.spine` to get authoritative reading order. Do NOT use `get_items_of_type(ITEM_DOCUMENT)` for chapter ordering — that returns manifest order which is not guaranteed to be reading order.

**When to use:** Always, for all chapter extraction.

```python
# Source: ebooklib GitHub issue #216 + official tutorial
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup

def get_chapters_in_order(book: epub.EpubBook) -> list[epub.EpubHtml]:
    chapters = []
    for item_id, linear in book.spine:
        item = book.get_item_with_id(item_id)
        if item is None:
            continue
        if item.get_type() == ebooklib.ITEM_DOCUMENT:
            chapters.append(item)
    return chapters
```

### Pattern 2: Hybrid Front Matter Detection

**What:** Three-tier detection: guide/landmarks element first (most reliable for well-formed EPUBs), then heading scan fallback, then include-everything fallback.

**When to use:** Front matter exclusion (PARSE-05).

```python
# Source: EPUB spec + epubsecrets.com + user constraint (include over exclude)

def find_story_start_index(book: epub.EpubBook, chapters: list[epub.EpubHtml]) -> int:
    """Return index of first chapter to include. 0 = include all."""

    # Tier 1: EPUB2 guide element (type="text" = "start of story")
    if hasattr(book, 'guide') and book.guide:
        for guide_ref in book.guide:
            if guide_ref.get('type', '').lower() in ('text', 'bodymatter'):
                href = guide_ref.get('href', '').split('#')[0]
                for i, ch in enumerate(chapters):
                    if ch.get_name().endswith(href) or href.endswith(ch.get_name()):
                        return i

    # Tier 2: Heading scan - first chapter with h1/h2 containing "chapter" or digit
    import re
    chapter_pattern = re.compile(r'\bchapter\b|\bpart\b|\bprologue\b', re.IGNORECASE)
    digit_pattern = re.compile(r'\b(one|two|three|1|2|3|i+)\b', re.IGNORECASE)
    for i, ch in enumerate(chapters):
        soup = BeautifulSoup(ch.get_body_content(), 'lxml')
        for tag in soup.find_all(['h1', 'h2']):
            text = tag.get_text(strip=True)
            if chapter_pattern.search(text) or digit_pattern.search(text):
                return i

    # Tier 3: Include everything (user's stated preference)
    return 0
```

### Pattern 3: Dialogue Detection with Quotation Mark Variants

**What:** Regex that covers both straight (`"`) and curly (`"` `"`) double quotes, and optionally single curly quotes (`'` `'`). Fiction EPUBs use either convention.

**When to use:** During segment type classification (PARSE-03, PARSE-04).

```python
# Source: Python re module docs + Unicode quotation mark research
import re

# Matches text within double quotes (straight or curly) or single curly quotes
DIALOGUE_PATTERN = re.compile(
    r'(?:[\u201c"]\s*.+?\s*[\u201d"])'  # "text" or \u201ctext\u201d
    r"|(?:[\u2018']\s*.+?\s*[\u2019'])",  # 'text' (curly single only, avoid contractions)
    re.DOTALL
)

def classify_paragraph(text: str, html_tag_name: str) -> str:
    """Returns: 'dialogue', 'narration', 'chapter_heading', or 'scene_break'"""
    stripped = text.strip()

    # Scene break: asterisks, dinkus, em-dash separators, blank/whitespace-only
    SCENE_BREAK_PATTERN = re.compile(r'^[\*\-\u2014\u2013#~\s]{1,10}$|^\*\s*\*\s*\*$')
    if not stripped or SCENE_BREAK_PATTERN.match(stripped):
        return 'scene_break'

    # Chapter heading: h1, h2, h3 tags or very short text in heading context
    if html_tag_name in ('h1', 'h2', 'h3', 'h4'):
        return 'chapter_heading'

    # Dialogue: paragraph that is primarily (>50%) quotation content
    if DIALOGUE_PATTERN.search(stripped):
        return 'dialogue'

    return 'narration'
```

### Pattern 4: Segment Splitting with Character Limit

**What:** NLTK punkt splits paragraphs into sentences; each sentence becomes a segment. Long sentences get clause-boundary splits. Confirmed ceiling: 280 characters (buffer below Chatterbox's 300-char limit).

**When to use:** Converting chapter text to segments (PARSE-06).

```python
# Source: NLTK docs + Chatterbox limit research (300 char hard limit, 280 safe ceiling)
import nltk
from nltk.tokenize import sent_tokenize

CHAR_LIMIT = 280  # Safe ceiling for Chatterbox TTS (~300 char hard limit)
CLAUSE_BOUNDARIES = re.compile(r'(?<=[,;])\s+|(?<=\u2014)\s*|(?<=--)\s*')

def split_to_segments(text: str, segment_type: str) -> list[str]:
    """Split text into TTS-safe segments. Returns list of strings <= CHAR_LIMIT chars."""
    sentences = sent_tokenize(text)
    segments = []
    for sentence in sentences:
        if len(sentence) <= CHAR_LIMIT:
            segments.append(sentence)
        else:
            # Force-split at clause boundaries
            parts = CLAUSE_BOUNDARIES.split(sentence)
            current = ''
            for part in parts:
                if len(current) + len(part) <= CHAR_LIMIT:
                    current = (current + ' ' + part).strip() if current else part
                else:
                    if current:
                        segments.append(current)
                    current = part
            if current:
                segments.append(current)
    return segments
```

### Pattern 5: Typer Multi-Command CLI

**What:** Single `main.py` with `app = typer.Typer()` and one `@app.command()` per phase plus a `convert` orchestrator command.

**When to use:** CLI entry point (CLI-01, CLI-02).

```python
# Source: typer.tiangolo.com/tutorial/commands/
import typer
from rich.progress import track
from rich import print as rprint
from pathlib import Path

app = typer.Typer(no_args_is_help=True)

@app.command()
def parse(epub_file: Path = typer.Argument(..., help="Path to EPUB file")):
    """Parse EPUB into segments.json."""
    rprint(f"[bold]Parsing[/bold] {epub_file.name}...")
    # Implementation calls src/parser/
    ...

@app.command()
def attribute(book_dir: Path = typer.Argument(...)):
    """Attribute dialogue speakers using local LLM."""
    ...

@app.command()
def convert(epub_file: Path = typer.Argument(..., help="Path to EPUB file")):
    """Run full pipeline end-to-end (parse → attribute → match → synthesize → assemble)."""
    rprint("[bold cyan]Starting full pipeline...[/bold cyan]")
    # Chain all phases without confirmation prompts
    ...

if __name__ == "__main__":
    app()
```

### Pattern 6: Segment Data Model and JSON Output

**What:** Python dataclass for segment, serialized with `dataclasses.asdict()` + `json.dump`.

**When to use:** PARSE-07 — producing `segments.json`.

```python
# Source: Python stdlib docs
from dataclasses import dataclass, asdict
from enum import Enum
import json
from pathlib import Path

class SegmentType(str, Enum):
    NARRATION = "narration"
    DIALOGUE = "dialogue"
    CHAPTER_HEADING = "chapter_heading"
    SCENE_BREAK = "scene_break"

@dataclass
class Segment:
    id: int                   # Sequential global ID
    chapter: int              # 1-based chapter number
    chapter_title: str        # e.g. "Chapter 1" or "" for untitled
    type: str                 # SegmentType value
    text: str                 # Clean, speech-ready text
    char_count: int           # len(text)

def write_segments_json(segments: list[Segment], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump([asdict(s) for s in segments], f, ensure_ascii=False, indent=2)
```

### Pattern 7: ebooklib Warning Suppression

**What:** ebooklib 0.20 emits a `UserWarning` about `ignore_ncx` on every `read_epub` call. Suppress it proactively.

**When to use:** Any `epub.read_epub()` call.

```python
# Source: ebooklib GitHub issue #296
import warnings

def read_epub_clean(path: str) -> epub.EpubBook:
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=UserWarning, module="ebooklib")
        return epub.read_epub(path, options={'ignore_ncx': True})
```

### Pattern 8: Rich Progress for Chapter Processing

**What:** Rich `track()` wraps chapter iteration for visual progress; `rprint` with markup for colored summary.

**When to use:** During parse command execution.

```python
# Source: rich.readthedocs.io/en/latest/progress.html + typer docs
from rich.progress import track
from rich import print as rprint

def parse_epub_with_progress(chapters):
    all_segments = []
    for chapter in track(chapters, description="Parsing chapters..."):
        segments = process_chapter(chapter)
        all_segments.extend(segments)

    dialogue_count = sum(1 for s in all_segments if s.type == 'dialogue')
    rprint(f"\n[green]Done![/green] "
           f"[bold]{len(chapters)}[/bold] chapters · "
           f"[bold]{len(all_segments)}[/bold] segments · "
           f"[bold]{dialogue_count}[/bold] dialogue lines")
    return all_segments
```

### Anti-Patterns to Avoid

- **`get_items_of_type(ITEM_DOCUMENT)` for reading order:** Returns manifest order, not spine order. Always use `book.spine` + `get_item_with_id()` instead.
- **`html.parser` as BS4 backend for EPUB content:** BS4 docs rank it 3rd. EPUB XHTML is frequently malformed XML; lxml is more tolerant and faster.
- **Regex for sentence splitting:** Breaks on "Dr.", "Mr.", "U.S." — common in fiction. Use NLTK punkt instead.
- **`soup.get_text()` on full document:** Includes `<head>` content, style attributes, and script tags. Use `get_body_content()` first, then BeautifulSoup on just the body HTML.
- **Not stripping `linear="no"` spine items:** EPUB spine items marked non-linear (footnotes, endnotes, cover pages) should typically be skipped in reading flow.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Sentence boundary detection | Custom regex tokenizer | `nltk.sent_tokenize` (punkt) | Regex fails on abbreviations (Dr., Mrs., Jr., U.S.) and ellipses; punkt is trained on English prose and handles these |
| HTML to plain text | String replace / regex strip | BeautifulSoup `get_text()` on body content | XHTML in EPUBs has nested spans, ruby annotations, footnotes, sidebars; manual stripping misses edge cases |
| EPUB container parsing | ZipFile + manual OPF parsing | ebooklib | EPUB is a zip with OPF manifest, spine, NCX/nav, and guide; ebooklib handles EPUB2 vs EPUB3 differences transparently |
| Colored terminal output | ANSI escape codes | `typer.secho()` or `rich.print()` | ANSI codes break on Windows terminal and some CI environments; Rich handles this correctly |
| Progress display | Print statements with `\r` | `rich.progress.track()` | Race conditions, no cleanup on error, doesn't handle stderr |

**Key insight:** EPUB internals (OPF, NCX, nav documents, guide elements) vary significantly between EPUB2 and EPUB3 and between publishers. ebooklib abstracts this; any hand-rolled solution will encounter publisher-specific edge cases that ebooklib already handles.

---

## Common Pitfalls

### Pitfall 1: Manifest Order vs. Spine Order (HIGH SEVERITY)

**What goes wrong:** Using `book.get_items_of_type(ebooklib.ITEM_DOCUMENT)` returns chapters in the order they appear in `content.opf` under `<manifest>`, which may not match reading order. Some EPUBs — especially multi-book compilations and some commercial EPUBs — have manifest and spine in different orders.

**Why it happens:** ebooklib's `get_items()` family iterates the manifest dictionary. The spine is a separate ordered list that references manifest items by ID.

**How to avoid:** Always iterate `book.spine` and look up items via `book.get_item_with_id(item_id)`. See Pattern 1.

**Warning signs:** Chapters appear out of order in output; a book that starts mid-story.

### Pitfall 2: ebooklib `UserWarning` on Every EPUB Load

**What goes wrong:** ebooklib 0.20 warns: "In the future version we will turn default option ignore_ncx to True." This clutters CLI output and appears as a bug to users.

**Why it happens:** ebooklib is transitioning its NCX handling default. The warning fires on every `read_epub()`.

**How to avoid:** Pass `options={'ignore_ncx': True}` and wrap with `warnings.filterwarnings`. See Pattern 7.

**Warning signs:** Yellow warning text printed to stderr during parse.

### Pitfall 3: NLTK Punkt Model Not Downloaded

**What goes wrong:** `nltk.sent_tokenize()` raises `LookupError: Resource punkt not found` on first run on a fresh machine.

**Why it happens:** NLTK requires a separate download step for its pre-trained models; they are not included in the package.

**How to avoid:** Add a startup check that downloads `punkt_tab` if not present. Run `nltk.download('punkt_tab', quiet=True)` at module import in `segmenter.py`. In newer NLTK versions (3.8+), the correct resource name is `punkt_tab` not `punkt`.

**Warning signs:** LookupError on first run; works after `nltk.download()` is called manually.

### Pitfall 4: EPUB3 NCX vs. Nav Document TOC

**What goes wrong:** ebooklib may read TOC from the legacy NCX file in an EPUB3 book that includes both NCX (for backwards compatibility) and a nav document. The NCX may have different chapter titles or ordering than the nav document.

**Why it happens:** ebooklib historically preferred the NCX. The `ignore_ncx=True` option forces it to use the nav document for EPUB3.

**How to avoid:** Use `options={'ignore_ncx': True}` when reading EPUB3 files (or always, as a safe default).

**Warning signs:** Chapter titles in output don't match the book's actual chapter names.

### Pitfall 5: `soup.get_text()` Includes Navigation Content

**What goes wrong:** If BeautifulSoup is called on `item.get_content()` (full HTML document) rather than `item.get_body_content()`, nav elements, script content, and head metadata appear in extracted text.

**Why it happens:** EPUB XHTML documents include `<head>`, sometimes with inline scripts or metadata that BS4 includes in `get_text()`.

**How to avoid:** Always call `item.get_body_content()` first to get only body HTML, then pass that to BeautifulSoup. Then call `soup.get_text(separator=' ', strip=True)` on specific paragraph/block tags rather than the whole tree.

**Warning signs:** "Chapter 1" output starts with CSS class names, JavaScript snippets, or metadata strings.

### Pitfall 6: Dialogue Spanning Multiple Paragraphs

**What goes wrong:** A character's speech may span several paragraphs in the source HTML (no closing quote until the final paragraph). Each intermediate paragraph appears to be mid-dialogue without closing quotes, causing misclassification.

**Why it happens:** Publishers use the convention of no closing quote on non-final paragraphs of extended speech to signal the same speaker is still talking.

**How to avoid:** Track open/close quote state across paragraphs within a chapter. If a paragraph opens a quote but doesn't close it, mark it as dialogue and carry forward the open-quote state to the next paragraph. Reset state at chapter boundaries.

**Warning signs:** Narration segments that begin mid-sentence with lowercase text; no closing quote on paragraph.

### Pitfall 7: Scene Break Misclassification

**What goes wrong:** EPUB publishers use many different scene break conventions: `***`, `* * *`, `---`, `— ◆ —`, a single `#`, blank paragraphs, or CSS-styled horizontal rules (`<hr>`). Plain text extraction loses CSS context, and whitespace-only paragraphs may be invisible.

**Why it happens:** EPUBs encode scene breaks inconsistently; some rely on `<hr>` tags, others on styled `<p>` with asterisks, others on empty paragraphs.

**How to avoid:** Detect scene breaks by checking: (1) `<hr>` tags, (2) paragraphs containing only repetitions of `*`, `-`, `~`, `#`, em-dash, or whitespace, (3) paragraphs with CSS class names containing "break", "separator", or "divider" (check class attribute before stripping HTML).

**Warning signs:** `scene_break` segments appear with text content; actual scene breaks are tagged as `narration`.

---

## Code Examples

Verified patterns from official sources and confirmed ebooklib behavior:

### Complete EPUB Load and Spine Walk

```python
# Source: ebooklib GitHub issue #216, official tutorial
import ebooklib
import warnings
from ebooklib import epub
from bs4 import BeautifulSoup

def load_epub(path: str) -> tuple[epub.EpubBook, list[epub.EpubHtml]]:
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=UserWarning, module="ebooklib")
        book = epub.read_epub(path, options={'ignore_ncx': True})

    chapters = []
    for item_id, linear in book.spine:
        item = book.get_item_with_id(item_id)
        if item is None:
            continue
        if item.get_type() != ebooklib.ITEM_DOCUMENT:
            continue
        # Skip non-linear items (cover, endnotes, footnotes)
        if linear == 'no':
            continue
        chapters.append(item)

    return book, chapters
```

### XHTML to Clean Text

```python
# Source: bitsgalore.org EPUB extraction analysis + BS4 docs
def chapter_to_text_blocks(item: epub.EpubHtml) -> list[tuple[str, str]]:
    """Returns list of (tag_name, text) for each block element."""
    soup = BeautifulSoup(item.get_body_content(), 'lxml')
    blocks = []
    # Check for <hr> scene breaks before stripping
    for tag in soup.find_all(['p', 'div', 'h1', 'h2', 'h3', 'h4', 'hr', 'blockquote']):
        if tag.name == 'hr':
            blocks.append(('hr', ''))
            continue
        text = tag.get_text(separator=' ', strip=True)
        if text:
            blocks.append((tag.name, text))
    return blocks
```

### NLTK Sentence Tokenizer with Startup Download

```python
# Source: nltk.org docs
import nltk

def ensure_nltk_data():
    """Download punkt_tab if not present. Safe to call on every startup."""
    try:
        nltk.data.find('tokenizers/punkt_tab')
    except LookupError:
        nltk.download('punkt_tab', quiet=True)

# Call once at module load
ensure_nltk_data()
```

### Typer Command with Book Name Argument

```python
# Source: typer.tiangolo.com/tutorial/commands/
import typer
from pathlib import Path

app = typer.Typer(no_args_is_help=True)

@app.command()
def parse(
    epub_file: Path = typer.Argument(..., exists=True, help="Path to EPUB file"),
    output_dir: Path = typer.Option(Path("output"), help="Output directory"),
):
    """Parse EPUB into segments.json."""
    book_slug = epub_file.stem.lower().replace(' ', '-')
    book_output = output_dir / book_slug
    book_output.mkdir(parents=True, exist_ok=True)
    typer.secho(f"Parsing: {epub_file.name}", fg=typer.colors.CYAN, bold=True)
    # ... call parser ...
    typer.secho(f"Output: {book_output}/segments.json", fg=typer.colors.GREEN)
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `get_items_of_type(ITEM_DOCUMENT)` | `book.spine` iteration | ebooklib docs updated ~2021 | Reading order correctness; critical for multi-book EPUBs |
| `nltk.download('punkt')` | `nltk.download('punkt_tab')` | NLTK 3.8+ | Old resource name still works via compatibility shim but generates deprecation warning |
| html.parser as BS4 backend | lxml | Long-standing recommendation | Faster, handles malformed XHTML better |
| EPUB2 guide element | EPUB3 landmarks nav | EPUB3 spec (2014) | Both still used; ebooklib exposes `book.guide` for EPUB2 compat |

**Deprecated/outdated:**
- `ebooklib.ITEM_DOCUMENT` iteration for reading order: Not deprecated but incorrect for ordering — must use spine.
- `nltk.download('punkt')`: Works but `punkt_tab` is the correct name for NLTK 3.8+.

---

## Discretion Recommendations

### Character Limit Ceiling

**Recommendation: 280 characters.** Chatterbox's hard limit is ~300 characters (confirmed by its Hugging Face Space UI and community audiobook projects). The PROJECT.md already documents "keeping chunks under 280 chars" as the project standard. A 20-character safety buffer accounts for voice drift that can occur near the limit. Do not change this.

### Chapter Detection Strategy

**Recommendation: Hybrid (guide/landmarks → heading scan → include all).**

- EPUB guide element (`type="text"`) is reliable for professionally published fiction EPUBs (major publishers include it). This covers the majority case.
- Heading scan (`<h1>`/`<h2>` containing "Chapter", "Part", "Prologue", or Roman numerals) handles well-structured EPUBs that lack a guide element.
- Include-everything fallback respects the user's stated preference to never miss story content.

The spine-based `linear="no"` filter handles obvious non-story content (cover, navigation) regardless of which tier triggers.

### Additional Segment Types

**Recommendation: Do not add a 5th segment type for internal monologue in Phase 1.** Rationale:

- Phase 2 (LLM attribution) is better positioned to distinguish internal monologue from third-person narration — it has full story context.
- Italic detection via `<em>` or `<i>` tags is unreliable in EPUBs: publishers use `<em>` for both emphasis and italics; not all internal monologue is italicized.
- The four base types (narration, dialogue, chapter_heading, scene_break) are sufficient for Phase 1's contract — Phase 2 can annotate further.

Keeping four types reduces parser complexity and avoids introducing a type that downstream phases don't yet support.

### Output Directory Naming

**Recommendation:** `output/{epub-stem-as-slug}/segments.json`

- `epub-stem-as-slug`: `epub_file.stem.lower().replace(' ', '-').replace('_', '-')` — no special characters, filesystem-safe.
- Example: `the-name-of-the-wind.epub` → `output/the-name-of-the-wind/segments.json`
- Keep it simple; do not include timestamps or hash suffixes (makes re-runs overwrite cleanly, which is the correct behavior for a single-user personal tool).

---

## Open Questions

1. **EPUB3 landmarks access via ebooklib**
   - What we know: ebooklib exposes `book.guide` for EPUB2 guide elements. The EPUB3 landmarks nav is a nav document item with `epub:type="landmarks"`.
   - What's unclear: Whether ebooklib parses EPUB3 landmarks into `book.guide` automatically or requires manual extraction from the nav document HTML.
   - Recommendation: During implementation, test with both EPUB2 and EPUB3 samples. If `book.guide` is empty for EPUB3, parse the nav item manually with BeautifulSoup looking for `<a epub:type="bodymatter">` links.

2. **Paragraph-spanning dialogue state machine correctness**
   - What we know: Publishers use the open-quote convention for multi-paragraph speech (no closing quote on non-final paragraphs).
   - What's unclear: How common this is in the specific EPUB files this project will process; whether false positives (narration misclassified as dialogue) are worse than false negatives for Phase 2's LLM attribution.
   - Recommendation: Implement the state machine (Pitfall 6). Phase 2's LLM attribution will correct any misclassification, so false positives are acceptable in Phase 1. Track open-quote state within chapters only; reset at chapter boundaries.

3. **Chatterbox behavior at exactly 280 characters vs. longer segments**
   - What we know: Hard limit is ~300 chars from official UI; 280 is documented in PROJECT.md as the safe ceiling.
   - What's unclear: Whether there are quality differences at 250 vs. 280 for MPS inference on M4.
   - Recommendation: Use 280 as coded in REQUIREMENTS.md. If Phase 4 reveals quality issues at longer segments during development, adjust the constant in one place (`CHAR_LIMIT` in `segmenter.py`).

---

## Sources

### Primary (HIGH confidence)

- ebooklib 0.20 on PyPI (pypi.org/project/EbookLib/) — version, Python compat, confirmed 2026-03-03
- ebooklib GitHub issue #216 (github.com/aerkalov/ebooklib/issues/216) — spine ordering confirmation from maintainer
- ebooklib DeepWiki (deepwiki.com/aerkalov/ebooklib/2.2-reading-epub-files) — complete API reference including `book.guide`, `book.spine`, `get_body_content()`
- Typer 0.24.1 on PyPI (pypi.org/project/typer/) — version, Python >=3.10, dependencies, confirmed 2026-03-03
- Typer docs: commands tutorial (typer.tiangolo.com/tutorial/commands/) — `@app.command()` pattern
- Typer docs: progress bar (typer.tiangolo.com/tutorial/progressbar/) — `track()` recommendation
- Typer docs: printing/colors (typer.tiangolo.com/tutorial/printing/) — Rich-first recommendation
- Rich 14.3.3 on PyPI (pypi.org/project/rich/) — version, Python >=3.8, confirmed 2026-03-03
- PROJECT.md (project repo) — confirms "~300 character limit per generation call, segments under 280 chars"
- EPUBSecrets: EPUB guide element (epubsecrets.com) — `type="text"` as bodymatter reference

### Secondary (MEDIUM confidence)

- bitsgalore.org EPUB extraction analysis (2023) — confirmed ebooklib requires manual HTML iteration; no built-in extraction; lxml recommendation
- NLTK docs (nltk.org/api/nltk.tokenize.html) — `sent_tokenize()`, `punkt_tab` resource name
- EPUB spec landmarks (kb.daisy.org/publishing/docs/navigation/landmarks.html) — bodymatter landmark type
- ebooklib GitHub issue #296 — `ignore_ncx` warning and suppression approach
- Rich progress docs (rich.readthedocs.io/en/latest/progress.html) — Rich 14.1.0 track() API

### Tertiary (LOW confidence, flagged for validation)

- Chatterbox 300-character limit: confirmed by multiple sources (HuggingFace Space UI, petermg/Chatterbox-TTS-Extended README motivation, chatterbox-Audiobook project) but not in official resemble-ai/chatterbox README — verify during Phase 4 implementation
- EPUB3 landmarks vs. ebooklib `book.guide`: behavior not explicitly documented for EPUB3 case — verify with test EPUBs during implementation

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries verified on PyPI with version and Python compat
- Architecture: HIGH — patterns derived from official docs and confirmed GitHub issue discussions
- Pitfalls: HIGH (ordering, warnings, NLTK download) / MEDIUM (dialogue state machine, scene break variants) — common patterns from EPUB parsing community
- Chatterbox char limit: MEDIUM — confirmed by multiple community sources but not official API docs

**Research date:** 2026-03-03
**Valid until:** 2026-06-03 (stable libraries; ebooklib, Typer, Rich are not fast-moving)
