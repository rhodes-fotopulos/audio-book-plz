# Feature Research

**Domain:** Local EPUB-to-audiobook pipeline (multi-voice, LLM-attributed, voice-cloned)
**Researched:** 2026-03-03
**Confidence:** MEDIUM — competitor analysis is HIGH; multi-voice dialogue attribution is MEDIUM (emerging space, few mature tools)

## Feature Landscape

### Table Stakes (Users Expect These)

Features a tool in this space must have or it feels unfinished — even for personal use.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| EPUB parsing with chapter extraction | Every comparable tool does this; it's the entry point | MEDIUM | ebooklib + BeautifulSoup4 required. Must handle EPUB2 (NCX) and EPUB3 (XHTML nav). Filter front matter, copyright, TOC pages — these are frequent noise sources in fiction EPUBs. |
| Ordered, speech-ready text output | Raw HTML from EPUB is not speakable; cleaning is mandatory | MEDIUM | Strip tags, expand abbreviations, normalize punctuation. Sentence boundary detection needed for TTS chunking. |
| Single narrator TTS synthesis | Baseline capability of every existing tool (epub2tts, epub_to_audiobook, ebook2audiobook, abogen) | LOW | Already selected Chatterbox TTS. Baseline is narrating full text with one voice. |
| Chapter-level audio output | Standard convention; users expect one file per chapter minimum | LOW | Per-chapter WAV/MP3 as intermediate artifact. Chapter boundaries come from EPUB TOC. |
| Full-book assembled audio | Consolidated output is expected — listeners want one file or a clean sequence | LOW | pydub + ffmpeg assembly. MP3 at 128kbps is acceptable for voice-only content. |
| Checkpoint/resume for long runs | A typical novel (~80K words) takes 3-11 hours; interruption recovery is non-negotiable | MEDIUM | Per-segment WAV intermediates enable this. Resume must detect completed segments and skip re-generation. |
| CLI interface | Every serious pipeline tool is CLI-first; headless operation is expected for batch use | LOW | Already specified. Phase-level invocation (parse, attribute, synthesize, assemble) is the right model. |
| Basic progress reporting | Silent tools feel broken during multi-hour runs | LOW | tqdm or simple print-based progress per segment/chapter is sufficient. |
| Correct audio metadata (title, author, chapter names) | Audiobookshelf/Plex use ID3 tags for library organization; untagged files feel raw | LOW | mutagen or eyeD3 for MP3 tagging. Embed title, author, chapter number, chapter name at minimum. |

### Differentiators (Competitive Advantage)

Features that no existing open-source tool does well, and which define the core value of this project.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| LLM-based character extraction | No existing EPUB-to-audiobook tool extracts characters automatically from fiction text | HIGH | Ollama + Qwen 3 8B. Prompt must handle large casts (fantasy novels can have 40+ named characters), aliases, and unreliable narrators. Output is a character profile list with voice trait descriptions. |
| LLM-based dialogue speaker attribution | The defining feature; no current open-source tool attributes per-line dialogue to a character automatically at book scale | HIGH | Most tools (epub2tts, epub_to_audiobook) require manual chapter-level voice assignment at best. Alexandria does per-line annotation but only supports .txt/.md — not EPUB. audiobook-creator does attribution but via cloud LLM APIs. This project does it locally, on EPUB, at scale. |
| Voice cloning from real human recordings (LibriTTS-P) | Characters get voices from 2,443 real human recordings rather than synthetic presets | HIGH | Chatterbox requires ~10s reference clip. LibriTTS-P provides clean 24kHz audiobook-quality clips with annotated voice traits (gender, pitch, warmth, pace). Trait-to-speaker matching is the novel element. |
| LLM-based voice-character matching | Character traits described in prose matched to real speaker traits via LLM reasoning | HIGH | "A gruff, deep-voiced soldier" → finds LibriTTS-P speaker with matching annotation. Sentence-transformer embedding similarity as fallback for large casts. No existing tool does this. |
| Per-segment audio intermediates with speaker identity | Each WAV knows which character spoke it; enables debugging, re-synthesis of individual segments | MEDIUM | Naming convention: `ch01_seg042_narrator.wav`, `ch01_seg043_aragorn.wav`. Enables targeted re-runs when a voice assignment is wrong. |
| Sequential LLM/TTS phase isolation | Deliberate memory budget management — LLM and TTS never co-reside in memory | MEDIUM | Unique to this project's hardware constraint (16GB unified memory). Phase boundaries are explicit checkpoints. Other tools don't document this because they assume cloud or multi-GPU systems. |
| Narration vs. dialogue tagging | Text segments classified as narrator or character before synthesis; narrator gets a consistent anchor voice | MEDIUM | Ensures the "storytelling feel" — narrator voice is stable across entire book, character voices are distinct. No existing tool separates narrator from character at this granularity automatically. |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem useful but should be deliberately excluded from this project.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| GUI / Web interface | Lowers the "barrier to use" for casual users | Adds weeks of scope, diverges from CLI-first personal tool, Gradio/web adds dependencies. This is not a product for others. | CLI with clear --help output and phase-level commands is sufficient. |
| Real-time streaming output | Feels modern, reduces waiting | Requires fundamentally different pipeline architecture; Chatterbox is not streaming-first; the sequential LLM→TTS constraint makes streaming impractical | Batch processing with good progress reporting. |
| Cloud TTS fallback (ElevenLabs, OpenAI, Azure) | Better voice quality, more languages | Defeats the privacy and cost goals; introduces API keys, rate limits, and network dependency; makes this a different product | Stay fully local. Chatterbox quality is sufficient for personal listening. |
| Multi-language support | Useful for non-English libraries | Qwen 3 8B and Chatterbox are both primarily English-optimized; LibriTTS-P is English-only; adds complexity without personal value | English-only for v1. Document as a known limitation. |
| Automated audiobook distribution / upload | "One click to publish" sounds appealing | This is personal use; publishing is out of scope and adds legal/rights complexity | Output to local file system. User handles their own library management. |
| Emotional tone synthesis / prosody control | Makes characters sound more expressive | Chatterbox's emotion exaggeration control exists but is per-generation; calibrating it per character without listening tests adds unpredictable quality variance | Rely on Chatterbox's default naturalness, which is already high for cloned voices. Revisit as a v2 enhancement after baseline quality is validated. |
| OCR for scanned PDFs | Some books only exist as scans | Adds Tesseract/OCR dependency, significant preprocessing complexity, and quality unpredictability; fiction EPUBs don't need it | EPUB-only for v1. |
| Real-time re-attribution correction (interactive) | Fix wrong speaker assignments mid-run | Requires interactive session management, breaks the batch pipeline model | Make intermediate JSON attribution files human-editable. A user can correct and re-run from the synthesis phase. |
| Voice style per-chapter variation | Character sounds slightly different chapter by chapter | Creates voice inconsistency that breaks listener immersion — one of the key criticisms of early AI audiobooks | Fix voice cloning reference per character at the start, reuse it identically for all segments. |

## Feature Dependencies

```
[EPUB Parsing]
    └──requires──> [Speech-ready text segments]
                       └──requires──> [LLM character extraction]
                       |                  └──requires──> [LLM dialogue attribution]
                       |                                     └──requires──> [Voice-character matching]
                       |                                                        └──requires──> [TTS synthesis]
                       |                                                                           └──requires──> [Audio assembly]
                       └──requires──> [Narration/dialogue tagging]
                                          └──feeds──> [LLM dialogue attribution]

[Checkpoint/resume]
    └──requires──> [Per-segment WAV intermediates]
                       └──requires──> [TTS synthesis]

[Audio metadata]
    └──requires──> [Chapter extraction from EPUB]
    └──enhances──> [Audio assembly]

[Voice cloning from LibriTTS-P]
    └──requires──> [Voice-character matching]
    └──feeds──> [TTS synthesis]

[LLM dialogue attribution] ──conflicts──> [LLM character extraction running simultaneously]
[TTS synthesis] ──conflicts──> [LLM character extraction running simultaneously]
```

### Dependency Notes

- **EPUB parsing requires speech-ready text:** Raw EPUB HTML is not directly usable by LLM or TTS; cleaning and segmentation must happen first.
- **Character extraction requires speech-ready text:** The LLM needs clean prose to identify characters reliably; HTML noise produces hallucinated characters.
- **Dialogue attribution requires character extraction:** You can't attribute a line to a character you haven't identified.
- **Voice-character matching requires character extraction:** Character profiles (voice traits from the LLM) are the input to the matching step.
- **TTS synthesis requires voice-character matching:** Each segment needs a reference clip before synthesis can proceed.
- **Audio assembly requires TTS synthesis:** All segments must be complete before assembly can produce chapter files.
- **Checkpoint/resume requires per-segment WAV intermediates:** Without per-segment artifacts, resume means restarting from scratch.
- **LLM attribution conflicts with TTS synthesis (memory):** The sequential phase model exists precisely because both exceed 4GB GPU memory and cannot co-reside on a 16GB system.

## MVP Definition

### Launch With (v1)

The minimum pipeline that delivers the core value: feed in an EPUB, get out a multi-voice audiobook.

- [ ] EPUB parsing — chapter extraction, HTML cleaning, text segmentation, front matter filtering
- [ ] LLM character extraction — named characters with voice trait descriptions from first N chapters
- [ ] LLM dialogue attribution — per-line speaker labels across full book
- [ ] Voice-character matching — LLM trait matching against LibriTTS-P annotations, embedding similarity fallback
- [ ] TTS synthesis — Chatterbox with per-character voice cloning, ~280-char chunking, MPS acceleration
- [ ] Audio assembly — chapter MP3s + full book MP3, ID3 metadata embedded
- [ ] Checkpoint/resume — detect completed segments, skip re-generation on restart
- [ ] CLI with phase-level invocation — full pipeline or individual phases
- [ ] Basic progress reporting — per-segment, per-chapter progress output

### Add After Validation (v1.x)

Features to add once the baseline pipeline produces listenable output.

- [ ] Human-editable attribution JSON — structured output that a user can correct before re-running synthesis (trigger: first book where attribution errors are noticeable)
- [ ] Custom pronunciation overrides — a simple YAML file mapping character names / proper nouns to phonetic spelling (trigger: first fantasy novel with hard-to-pronounce names)
- [ ] Dry-run / preview mode — estimate segment count, synthesis time, and disk usage before committing to a full run (trigger: when processing a second book)
- [ ] Per-character voice sample playback — synthesize 3 seconds of each character's voice before full synthesis (trigger: when voice assignments feel wrong without listening)

### Future Consideration (v2+)

Features to defer until the v1 pipeline is proven reliable across multiple books.

- [ ] M4B output with embedded chapter markers — better player support (Audiobookshelf, Apple Books); defer because MP3-per-chapter is functional and M4B adds ffmpeg complexity
- [ ] Emotion/prosody annotation — Chatterbox emotion exaggeration per character type; defer because calibrating this without extensive listening tests risks degrading quality
- [ ] Larger LLM for attribution quality — swap Qwen 3 8B for a larger model or fine-tuned model for dialogue attribution; defer until v1 demonstrates where attribution errors occur
- [ ] Batch processing of a book library — process multiple EPUBs in sequence; defer until single-book pipeline is stable

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| EPUB parsing + segmentation | HIGH | MEDIUM | P1 |
| LLM character extraction | HIGH | MEDIUM | P1 |
| LLM dialogue attribution | HIGH | HIGH | P1 |
| Voice-character matching (LibriTTS-P) | HIGH | HIGH | P1 |
| Chatterbox TTS synthesis | HIGH | MEDIUM | P1 |
| Audio assembly (chapter + full book MP3) | HIGH | LOW | P1 |
| Checkpoint/resume | HIGH | MEDIUM | P1 |
| CLI phase invocation | HIGH | LOW | P1 |
| Progress reporting | MEDIUM | LOW | P1 |
| Audio metadata (ID3) | MEDIUM | LOW | P1 |
| Human-editable attribution JSON | MEDIUM | LOW | P2 |
| Custom pronunciation overrides | MEDIUM | LOW | P2 |
| Dry-run / preview mode | MEDIUM | LOW | P2 |
| Per-character voice preview | MEDIUM | LOW | P2 |
| M4B with chapter markers | LOW | MEDIUM | P3 |
| Emotion/prosody annotation | LOW | HIGH | P3 |
| Larger LLM swap | LOW | MEDIUM | P3 |
| Batch library processing | LOW | MEDIUM | P3 |

**Priority key:**
- P1: Must have for launch (v1)
- P2: Should have, add after validation (v1.x)
- P3: Nice to have, future consideration (v2+)

## Competitor Feature Analysis

Existing tools surveyed: epub_to_audiobook, epub2tts, ebook2audiobook, abogen, audiobook-maker, Alexandria, audiobook-creator.

| Feature | epub2tts | epub_to_audiobook | ebook2audiobook | Alexandria | audiobook-creator | This Project |
|---------|----------|-------------------|-----------------|------------|-------------------|--------------|
| EPUB parsing | Yes | Yes | Yes | No (.txt/.md only) | Yes | Yes |
| Chapter extraction | Yes | Yes | Yes | N/A | Yes | Yes |
| Single-voice TTS | Yes | Yes | Yes | Yes | Yes | Yes |
| Multi-voice (manual) | Yes (per-chapter) | No | Via SML tags | Yes (manual) | Yes (gender-based) | No — auto |
| LLM character extraction | No | No | No | Yes | Yes (cloud) | Yes (local) |
| LLM dialogue attribution | No | No | No | Yes (.txt only) | Yes (cloud) | Yes (EPUB, local) |
| Voice cloning | Yes (Coqui XTTS) | No | Yes | Yes (5-15s clip) | No | Yes (Chatterbox, LibriTTS-P) |
| Real human voice references | No | No | No | No | No | Yes (LibriTTS-P, 2443 speakers) |
| Trait-based voice matching | No | No | No | No | No | Yes (LLM + embeddings) |
| Checkpoint/resume | Yes | No | Yes | Partial | No | Yes |
| CLI | Yes | Yes | Yes | No (GUI only) | No (Gradio) | Yes |
| Local-only (no cloud) | Partial | No | Partial | No | No | Yes |
| M4B output | Yes | No | Yes | Yes | Yes | v2+ |
| MP3 output | Partial | Yes | Yes | Yes | Yes | Yes |
| Metadata embedding | Partial | Partial | Yes | Yes | Yes | Yes |

**Key insight:** No existing open-source tool does all of: EPUB parsing + local LLM attribution + LibriTTS-P voice cloning + CLI + checkpoint/resume. The combination is genuinely novel in the open-source space as of March 2026.

## Sources

- [GitHub: epub_to_audiobook (p0n1)](https://github.com/p0n1/epub_to_audiobook) — feature analysis via WebFetch, HIGH confidence
- [GitHub: epub2tts (aedocw)](https://github.com/aedocw/epub2tts) — feature analysis via WebFetch, HIGH confidence
- [GitHub: ebook2audiobook (DrewThomasson)](https://github.com/DrewThomasson/ebook2audiobook) — feature analysis via WebFetch, HIGH confidence
- [GitHub: Alexandria audiobook generator (Finrandojin)](https://github.com/Finrandojin/alexandria-audiobook) — feature analysis via WebFetch, MEDIUM confidence (newer project, docs may be incomplete)
- [GitHub: audiobook-creator (prakharsr)](https://github.com/prakharsr/audiobook-creator) — feature analysis via WebFetch, MEDIUM confidence
- [GitHub: abogen (denizsafak)](https://github.com/denizsafak/abogen) — discovered via WebSearch, feature summary from search result snippet, MEDIUM confidence
- [Chatterbox TTS (resemble-ai)](https://github.com/resemble-ai/chatterbox) — voice cloning and long-form features, MEDIUM confidence (WebSearch + official site)
- [M4B format and audiobook metadata](https://www.bookjack.app/blog/what-is-m4b-file-format/) — chapter markers, bookmarking, ID3 conventions, MEDIUM confidence
- [EPUB PLS pronunciation lexicon standard (W3C)](https://www.w3.org/TR/epub-tts-10/) — pronunciation dictionary conventions, HIGH confidence (official spec)
- [MultiActor-Audiobook paper (ISCA 2025)](https://www.isca-archive.org/interspeech_2025/park25e_interspeech.pdf) — academic reference for LLM-based speaker attribution in audiobooks, MEDIUM confidence
- [Audiobook narration user expectations (Spoken Press)](https://www.spoken.press/ai-audiobook-faq) — user acceptance of AI narration, LOW-MEDIUM confidence (market research)
- [ElevenLabs audiobook guide 2026](https://elevenlabs.io/blog/how-to-make-an-audiobook) — TTS feature expectations, LOW confidence (marketing source)

---
*Feature research for: EPUB-to-audiobook multi-voice pipeline*
*Researched: 2026-03-03*
