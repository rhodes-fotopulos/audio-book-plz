# Phase 1: EPUB Parsing and CLI Skeleton - Context

**Gathered:** 2026-03-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Parse any EPUB into clean, speech-ready JSON segments tagged by type, and wire up the CLI entry points for all five pipeline phases. This phase produces `segments.json` — the input artifact every downstream phase consumes. No LLM calls, no audio, no character attribution.

</domain>

<decisions>
## Implementation Decisions

### Segment splitting logic
- Split text at sentence boundaries — each sentence becomes its own segment
- If a single sentence exceeds the character limit, force-split at the nearest clause boundary (comma, semicolon, em-dash)
- Dialogue lines from one speaker are kept as a single segment when they fit within the limit; split only when they exceed it
- The 280-character limit is a soft target — Claude has discretion on the exact ceiling based on what Chatterbox handles best

### Front and back matter boundaries
- Exclude everything before Chapter 1 (title pages, copyright, ToC, dedications, prefaces)
- Include epilogues and afterwords (story-related endings) but exclude acknowledgments, author bios, reading guides, and excerpts from other books
- Chapter detection approach is Claude's discretion — pick the most robust method based on research
- When the parser can't confidently identify where the story starts (unusual EPUB structure), include everything rather than risk missing story content

### Special content types
- Poetry, song lyrics, and verse embedded in the novel: tag as narration — narrator reads them
- Letters, notes, and text messages from characters: tag as dialogue by the sender, so Phase 2 can attribute them to the right character's voice
- Chapter epigraphs (quotes at start of chapters): include as narration
- Whether to add segment types beyond the four (narration, dialogue, chapter_heading, scene_break) is Claude's discretion — e.g., internal monologue type if research supports it

### Output structure and CLI feel
- All output goes in a dedicated `output/` directory inside the project, organized by book name
- CLI shows progress during parsing (chapters being processed) followed by a summary (chapter count, segment count, dialogue line count)
- Use Typer as the CLI framework (type-hint based, auto-generated help, colored output)
- `python main.py convert book.epub` runs all phases automatically in one shot — no confirmation prompt, suitable for overnight unattended runs

### Claude's Discretion
- Exact character limit ceiling (280 is soft target — optimize for Chatterbox)
- Chapter detection strategy (EPUB spine order vs heading-based vs hybrid)
- Whether to add additional segment types beyond the base four
- Exact output directory naming conventions within `output/`

</decisions>

<specifics>
## Specific Ideas

- Letters and notes from characters should be voiced by the character who wrote them, not the narrator — tag them as dialogue so attribution works in Phase 2
- When in doubt about content boundaries, include rather than exclude — better to have extra content than miss part of the story
- CLI should feel modern (Typer, colored output, progress feedback) not bare-bones

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 01-epub-parsing-and-cli-skeleton*
*Context gathered: 2026-03-03*
