# Roadmap: Audio Book Plz

## Overview

A five-phase sequential pipeline that converts EPUB files into multi-voice audiobooks. Each phase produces typed JSON or audio artifacts that the next phase consumes — nothing skips ahead. The pipeline mirrors the five natural processing stages: parse the EPUB, attribute dialogue to characters, match characters to real human voices, synthesize audio per segment, then assemble chapters and the full audiobook MP3. The strict sequencing is an architectural constraint, not a preference — LLM and TTS models cannot share memory on the 16GB M4 Mac, so they are isolated into separate phases with explicit teardown at the boundary.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: EPUB Parsing and CLI Skeleton** - Parse any EPUB into clean, speech-ready JSON segments; wire up the CLI entry points for all pipeline phases
- [ ] **Phase 2: LLM Character Extraction and Speaker Attribution** - Extract character profiles from novel text and attribute every dialogue line to a character via local LLM
- [ ] **Phase 3: Voice-Character Matching** - Match each character to a real human voice from LibriTTS-P and lock the voice map before synthesis begins
- [ ] **Phase 4: TTS Synthesis with Checkpoint/Resume** - Synthesize per-segment WAV files using Chatterbox on Apple Silicon MPS with full crash recovery
- [ ] **Phase 5: Audio Assembly and Final Output** - Concatenate WAV segments into chapter and full-book MP3s with ID3 metadata

## Phase Details

### Phase 1: EPUB Parsing and CLI Skeleton
**Goal**: Users can feed any EPUB into the pipeline and get back a validated, speech-ready `segments.json` that all downstream phases can consume, with a working CLI to invoke each phase
**Depends on**: Nothing (first phase)
**Requirements**: PARSE-01, PARSE-02, PARSE-03, PARSE-04, PARSE-05, PARSE-06, PARSE-07, CLI-01, CLI-02
**Success Criteria** (what must be TRUE):
  1. User can run `python main.py parse book.epub` and get a `segments.json` with all chapters in reading order, front matter excluded
  2. Every segment in `segments.json` is tagged as narration, dialogue, chapter heading, or scene break, and no segment exceeds 280 characters
  3. Dialogue is correctly identified for both straight and curly quotation mark variants across representative fiction EPUBs
  4. User can run `python main.py [parse|attribute|match|synthesize|assemble]` to invoke any individual phase from the CLI
  5. User can run `python main.py convert book.epub` to trigger the full end-to-end pipeline with a single command
**Plans**: TBD

### Phase 2: LLM Character Extraction and Speaker Attribution
**Goal**: Users can hand the parser output to the LLM phase and get back a character registry and a fully attributed segment file where every dialogue line names its speaker
**Depends on**: Phase 1
**Requirements**: ATTR-01, ATTR-02, ATTR-03, ATTR-04, ATTR-05, ATTR-06
**Success Criteria** (what must be TRUE):
  1. User gets a `characters.json` containing every named character's profile (name, aliases, gender, age, voice qualities, personality) extracted from the novel text
  2. Character profiles correctly merge aliases across chapters — the same character does not appear under multiple entries in the registry
  3. Every segment in `attributed.json` has a speaker field: a character name from the registry, "narrator", or "unknown"
  4. Re-running attribution after partial completion skips chapters that are already cached and does not re-call the LLM for completed work
**Plans**: TBD

### Phase 3: Voice-Character Matching
**Goal**: Users can review and confirm which real human voice from LibriTTS-P is assigned to each character before any synthesis begins, with no two major characters sharing the same reference
**Depends on**: Phase 2
**Requirements**: VOICE-01, VOICE-02, VOICE-03, VOICE-04, VOICE-05
**Success Criteria** (what must be TRUE):
  1. User gets a `voice_map.json` that maps every character to a specific LibriTTS-P speaker with a clip path, produced by LLM trait comparison
  2. For casts that exceed LLM context, embedding similarity fallback kicks in automatically and produces assignments for all remaining characters
  3. No two major characters are assigned the same LibriTTS-P speaker reference
  4. Voice assignments persist across re-runs — re-running the match phase reads `voice_map.json` instead of re-querying the LLM
**Plans**: TBD

### Phase 4: TTS Synthesis with Checkpoint/Resume
**Goal**: Users can synthesize audio for all segments overnight, resume interrupted runs without re-generating completed segments, and track per-segment and per-chapter progress throughout
**Depends on**: Phase 3
**Requirements**: SYNTH-01, SYNTH-02, SYNTH-03, SYNTH-04, SYNTH-05, SYNTH-06, CLI-03, CLI-04
**Success Criteria** (what must be TRUE):
  1. User can run synthesis and get per-segment WAV files in a `wavs/` directory, with each segment voiced by its assigned character's reference clip via Chatterbox
  2. After an interrupted run, user can re-run the synthesis command and only unfinished segments are generated — completed WAVs are not regenerated
  3. Synthesis runs on MPS (Apple Silicon GPU) and stays within the 16GB memory budget — Ollama is confirmed unloaded before Chatterbox loads
  4. Progress is reported per-segment and per-chapter throughout the synthesis run so the user knows how much work remains
**Plans**: TBD

### Phase 5: Audio Assembly and Final Output
**Goal**: Users get a finished, listenable `audiobook.mp3` with correct silence spacing between segments, normalized volume, and ID3 metadata that audiobook players can read
**Depends on**: Phase 4
**Requirements**: AUDIO-01, AUDIO-02, AUDIO-03, AUDIO-04
**Success Criteria** (what must be TRUE):
  1. User gets a single `audiobook.mp3` file covering the entire book with all character voices assembled in chapter order
  2. Silence between segments is appropriate to the segment boundary type — sentences, paragraphs, and chapter breaks are audibly distinct
  3. Volume is consistent across different character voices throughout the audiobook — no one voice dominates or disappears
  4. The MP3 file contains ID3 metadata (title, author, chapter names) that audiobook players such as Audiobookshelf can read and display
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. EPUB Parsing and CLI Skeleton | 0/TBD | Not started | - |
| 2. LLM Character Extraction and Speaker Attribution | 0/TBD | Not started | - |
| 3. Voice-Character Matching | 0/TBD | Not started | - |
| 4. TTS Synthesis with Checkpoint/Resume | 0/TBD | Not started | - |
| 5. Audio Assembly and Final Output | 0/TBD | Not started | - |

---
*Roadmap created: 2026-03-03*
*Last updated: 2026-03-03 after initial roadmap creation*
