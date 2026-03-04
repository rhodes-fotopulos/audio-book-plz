# Requirements: Audio Book Plz

**Defined:** 2026-03-03
**Core Value:** Feed in an EPUB, get out a multi-voice audiobook where each character has a distinct, fitting voice cloned from a real human recording.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Parsing

- [ ] **PARSE-01**: User can parse an EPUB file (EPUB2 or EPUB3) and extract chapters in reading order
- [ ] **PARSE-02**: Parser strips HTML tags and produces clean, speech-ready text per chapter
- [ ] **PARSE-03**: Parser splits text into segments tagged as narration, dialogue, chapter heading, or scene break
- [ ] **PARSE-04**: Parser detects dialogue by identifying text within quotation marks (straight and curly variants)
- [ ] **PARSE-05**: Parser filters out front matter, copyright pages, TOC, and dedication pages
- [ ] **PARSE-06**: Parser splits segments exceeding 280 characters at sentence boundaries for TTS compatibility
- [ ] **PARSE-07**: Parser outputs ordered segments as JSON for downstream phases

### Attribution

- [ ] **ATTR-01**: User can extract character profiles (name, aliases, gender, age, voice qualities, personality) from novel text via local LLM
- [ ] **ATTR-02**: Character profiles accumulate across chapters, merging duplicates and aliases
- [ ] **ATTR-03**: Each dialogue line is attributed to a specific character or marked as "unknown" via local LLM
- [ ] **ATTR-04**: Narration segments are attributed to "narrator"
- [ ] **ATTR-05**: LLM processes chapters in chunks that fit within the context window (explicit num_ctx=32768)
- [ ] **ATTR-06**: Attribution results are cached per chapter so re-runs skip completed work

### Voice Matching

- [ ] **VOICE-01**: User can match characters to real human voices from the LibriTTS-P dataset (2,443 speakers)
- [ ] **VOICE-02**: LLM compares character voice traits to LibriTTS-P speaker annotations to find best matches
- [ ] **VOICE-03**: Embedding similarity (sentence-transformers) serves as fallback for large casts where LLM context is tight
- [ ] **VOICE-04**: No two major characters are assigned the same voice reference
- [ ] **VOICE-05**: Voice assignments are saved to voice_map.json and cached for re-runs

### Synthesis

- [ ] **SYNTH-01**: User can synthesize audio for each text segment using Chatterbox TTS with the assigned voice reference
- [ ] **SYNTH-02**: TTS runs on MPS (Apple Silicon GPU) with CPU fallback for unsupported ops (FFT)
- [ ] **SYNTH-03**: Ollama is explicitly unloaded before TTS model loads to stay within 16GB memory budget
- [ ] **SYNTH-04**: Segments exceeding 280 characters are split at sentence boundaries and generated separately
- [ ] **SYNTH-05**: Synthesis supports checkpoint/resume — completed segments are skipped on restart
- [ ] **SYNTH-06**: Per-segment WAV files are written atomically (write to .tmp, rename) to prevent corruption

### Audio Output

- [ ] **AUDIO-01**: User gets a single full-audiobook MP3 file as final output
- [ ] **AUDIO-02**: Appropriate silence is inserted between segments (300ms sentences, 800ms paragraphs, 1500ms chapters)
- [ ] **AUDIO-03**: Audio is normalized for consistent volume across different voices
- [ ] **AUDIO-04**: MP3 files include ID3 metadata (title, author, chapter names)

### CLI & Operations

- [ ] **CLI-01**: User can run the full pipeline end-to-end with a single command (e.g., `python main.py convert book.epub`)
- [ ] **CLI-02**: User can run individual phases separately (parse, analyze, synthesize, assemble)
- [ ] **CLI-03**: User can resume an interrupted synthesis run without re-generating completed segments
- [ ] **CLI-04**: Progress is reported during synthesis (per-segment/chapter progress)

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Polish

- **POLISH-01**: User can edit attribution JSON by hand and re-run synthesis from that point
- **POLISH-02**: User can define custom pronunciation overrides via YAML for character names and proper nouns
- **POLISH-03**: User can run a dry-run that estimates segment count, synthesis time, and disk usage
- **POLISH-04**: User can preview each character's voice (3-second sample) before committing to full synthesis

### Enhanced Output

- **OUT-01**: User gets individual chapter MP3 files in addition to full audiobook
- **OUT-02**: Full audiobook exported as M4B with embedded chapter markers for player support
- **OUT-03**: Emotion/prosody controls per character type (exaggeration tuning)

### Scale

- **SCALE-01**: User can batch-process multiple EPUBs in sequence
- **SCALE-02**: Support for larger LLM models when hardware allows

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| GUI or web interface | CLI-only personal tool; GUI adds weeks of scope with no personal value |
| Real-time streaming output | Requires fundamentally different pipeline architecture; Chatterbox is not streaming-first |
| Cloud TTS fallback (ElevenLabs, OpenAI, Azure) | Defeats privacy and cost goals; introduces API keys and network dependency |
| Multi-language support | Qwen 3 8B, Chatterbox, and LibriTTS-P are all English-optimized; no personal need |
| OCR for scanned PDFs | Adds Tesseract dependency and quality unpredictability; EPUB-only is sufficient |
| Mobile app | Desktop-only personal tool |
| Automated distribution/upload | Personal use; publishing is out of scope |
| Per-chapter voice style variation | Creates voice inconsistency that breaks listener immersion |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| PARSE-01 | Phase 1 | Pending |
| PARSE-02 | Phase 1 | Pending |
| PARSE-03 | Phase 1 | Pending |
| PARSE-04 | Phase 1 | Pending |
| PARSE-05 | Phase 1 | Pending |
| PARSE-06 | Phase 1 | Pending |
| PARSE-07 | Phase 1 | Pending |
| CLI-01 | Phase 1 | Pending |
| CLI-02 | Phase 1 | Pending |
| ATTR-01 | Phase 2 | Pending |
| ATTR-02 | Phase 2 | Pending |
| ATTR-03 | Phase 2 | Pending |
| ATTR-04 | Phase 2 | Pending |
| ATTR-05 | Phase 2 | Pending |
| ATTR-06 | Phase 2 | Pending |
| VOICE-01 | Phase 3 | Pending |
| VOICE-02 | Phase 3 | Pending |
| VOICE-03 | Phase 3 | Pending |
| VOICE-04 | Phase 3 | Pending |
| VOICE-05 | Phase 3 | Pending |
| SYNTH-01 | Phase 4 | Pending |
| SYNTH-02 | Phase 4 | Pending |
| SYNTH-03 | Phase 4 | Pending |
| SYNTH-04 | Phase 4 | Pending |
| SYNTH-05 | Phase 4 | Pending |
| SYNTH-06 | Phase 4 | Pending |
| CLI-03 | Phase 4 | Pending |
| CLI-04 | Phase 4 | Pending |
| AUDIO-01 | Phase 5 | Pending |
| AUDIO-02 | Phase 5 | Pending |
| AUDIO-03 | Phase 5 | Pending |
| AUDIO-04 | Phase 5 | Pending |

**Coverage:**
- v1 requirements: 32 total
- Mapped to phases: 32
- Unmapped: 0

---
*Requirements defined: 2026-03-03*
*Last updated: 2026-03-03 after roadmap creation — all 32 requirements mapped*
