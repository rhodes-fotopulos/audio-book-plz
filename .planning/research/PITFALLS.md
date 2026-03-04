# Pitfalls Research

**Domain:** EPUB-to-multi-voice-audiobook pipeline (local Python, Ollama + Chatterbox TTS, M4 Mac)
**Researched:** 2026-03-03
**Confidence:** MEDIUM — Core pitfalls verified across multiple sources; Chatterbox MPS stability and Ollama context behaviour confirmed via GitHub issues and official docs. Some predictions are inference from analogous TTS/LLM pipeline experience where direct sources were sparse.

---

## Critical Pitfalls

### Pitfall 1: Chatterbox Hard 40-Second Audio Cutoff

**What goes wrong:**
Chatterbox's TTS engine has a hard architectural constraint that stops audio generation at approximately 40 seconds regardless of how much input text remains. Long passages passed as a single chunk produce truncated audio with no error — the output file silently ends mid-sentence. Attempts to tune internal timeout values produce instability beyond ~53 seconds.

**Why it happens:**
The constraint is baked into Chatterbox's flow-matching architecture, which operates on fixed-length latent representations. It was not designed for long-form generation. The ~300 character chunk recommendation exists precisely because of this, but developers often assume the limit is advisory rather than hard.

**How to avoid:**
Enforce a maximum chunk size of 250–280 characters (conservative margin below 300). Use recursive splitting at sentence boundaries first, then clause boundaries (`;`, `:`, `—`, `,`) as fallback. Never pass raw paragraphs without pre-splitting. Validate that no chunk exceeds the limit at pipeline entry, before synthesis begins.

**Warning signs:**
- Generated WAV files that end abruptly or are shorter than expected for the input length
- Output audio duration significantly less than (character_count / average_chars_per_second) estimate
- Silent tail-end in concatenated chapter audio

**Phase to address:**
Text Chunking phase (Parse/Preprocess stage). The chunker must be the gatekeeper — malformed chunks must never reach the TTS model.

---

### Pitfall 2: Chatterbox MPS Instability on Apple Silicon

**What goes wrong:**
Chatterbox TTS has experimental, buggy MPS support on Apple Silicon. Some dependency chains pin PyTorch versions that conflict with the MPS-capable PyTorch builds, causing import-time failures or silent fallback to CPU. Other issues include MPS tensor type mismatches mid-inference and scaled_dot_product_attention (SDPA) crashes under certain sequence lengths. Some community forks automatically disable MPS and run CPU-only for stability.

**Why it happens:**
Chatterbox was primarily developed and tested against CUDA (NVIDIA). MPS is a secondary target without the same test coverage. PyTorch's MPS backend has known memory regression bugs in 2025 (tracked in PyTorch issue tracker), particularly with SDPA on large sequences.

**How to avoid:**
- Install PyTorch with MPS support first, then install Chatterbox dependencies with `--no-deps` / manual conflict resolution
- Set `PYTORCH_ENABLE_MPS_FALLBACK=1` in the environment to prevent crashes from unsupported ops
- Set `model.config.attn_implementation="eager"` when SDPA causes instability
- Add a startup health-check: generate a 5-word test utterance before beginning a book run; fail loudly if MPS errors occur
- Keep a CPU fallback codepath with explicit device override

**Warning signs:**
- Import errors mentioning `mps` device or tensor type mismatches
- Inconsistent generation times (MPS silently falling back to CPU mid-session)
- `RuntimeError: MPS backend out of memory` during synthesis of longer passages

**Phase to address:**
Environment Setup / Synthesis phase. MPS configuration and health checks belong in the synthesis phase scaffolding before any real generation occurs.

---

### Pitfall 3: Ollama Default Context Window Silently Truncates Long Chapters

**What goes wrong:**
Ollama defaults to a 2048-token context window. Qwen 3 8B's default via Ollama is also frequently 4K tokens. A dense fiction chapter can easily exceed 4K tokens. When the context window is exhausted, Ollama silently truncates the input — the model never sees the later portions of the chapter — and returns attribution results that are partially hallucinated. The pipeline has no error; the output JSON looks valid but reflects only the first portion of the chapter.

**Why it happens:**
Local LLM wrappers like Ollama set conservative defaults to protect memory. The problem is invisible: no exception is raised, no warning is logged. Research from 2025 shows LLM performance degrades significantly well before the hard context limit — some models show accuracy drops starting at 1000 tokens in context.

**How to avoid:**
- Explicitly set `num_ctx` to at least 16K (32K preferred) when invoking Ollama for attribution tasks: `ollama run qwen3:8b --num-ctx 32768`
- Chunk chapters into segments of 2000–3000 words maximum before passing to the LLM for attribution
- Log token count estimates per request and alert if approaching 80% of configured context window
- Cross-validate attribution results: character names appearing in unattributed segments should trigger a re-attribution pass

**Warning signs:**
- Attribution results where dialogue in the second half of a chapter is consistently unattributed or attributed to "Unknown"
- LLM response time drops sharply partway through a book (indicating model is processing less text)
- Character names mentioned after the first 3000 words of a chapter never appear in speaker lists

**Phase to address:**
LLM Attribution phase. Context window configuration must be established and tested before any attribution runs against full chapters.

---

### Pitfall 4: LLM Dialogue Attribution Hallucination and Cascade Misattribution

**What goes wrong:**
The LLM misattributes a dialogue line — either to the wrong character or to a character not in the scene. In fiction, dialogue often spans multiple paragraphs without a speaker tag. The LLM infers attribution from narrative context, and when context is ambiguous or the model is uncertain, it confabulates a plausible-sounding speaker. All downstream synthesis for that segment then uses the wrong voice, creating an audio error that is very hard to detect without listening.

Cascade misattribution is worse: a wrong attribution in a multi-turn dialogue sequence causes the model to maintain an internally consistent but factually wrong alternation ("if A spoke last, B speaks next") — producing an entire exchange rendered in the wrong voices.

**Why it happens:**
8B parameter models handle straightforward attributed dialogue well but struggle with: (1) he-said/she-said inference across multiple paragraphs without explicit tags, (2) scenes with 3+ active speakers, (3) interior monologue rendered as direct thought (no quotation marks), (4) dialect-heavy dialogue where the model may mis-identify a voice pattern as a different character.

**How to avoid:**
- Use structured output (JSON schema enforcement) for Ollama responses to catch malformed attributions early
- Include the character list and brief descriptions in every attribution prompt — do not rely on the model's memory of earlier prompt context
- Flag "Unknown" attributions explicitly rather than silently assigning narrator voice; log them for human review
- For scenes with 3+ speakers, break the attribution window smaller (500-word chunks) to reduce ambiguity
- Post-attribution sanity check: any character appearing in the attribution list who was not established in the book's character registry should be flagged as a potential hallucination

**Warning signs:**
- Character names appearing in attribution results that were not in the pre-built character registry
- A character speaking dialogue in a chapter where they do not appear in the narrative
- Perfect alternation patterns (ABABAB) in multi-speaker scenes — natural dialogue is rarely this regular

**Phase to address:**
LLM Attribution phase AND Character Extraction phase (build a character registry first; validate all attributions against it).

---

### Pitfall 5: Memory Pressure Crash from Simultaneous Model Residency

**What goes wrong:**
On a 16GB unified memory M4 Mac, holding both Ollama (Qwen 3 8B, ~6–8GB quantized) and Chatterbox TTS models in memory simultaneously causes macOS memory pressure. The system begins aggressive memory compression, swap increases dramatically, and generation slows to near-CPU speeds. In worst cases, the Python process is OOM-killed mid-generation, corrupting the in-progress WAV file and leaving the checkpoint in an inconsistent state.

**Why it happens:**
Both models load weights into unified memory. Qwen 3 8B at Q4 quantization requires approximately 4.5–6GB. Chatterbox's flow-matching model plus vocoder requires 2–4GB. Together they approach or exceed the ~12GB available after macOS system reservation. The project already recognizes sequential phases, but the risk is that cleanup between phases is incomplete — Ollama may keep the model resident in memory even after the attribution phase completes.

**How to avoid:**
- Explicitly unload the Ollama model after the attribution phase: `ollama stop qwen3:8b` or use the REST API `DELETE /api/delete` equivalent (keep-alive = 0)
- Verify model is unloaded before starting Chatterbox synthesis: check `ollama ps` output and assert empty
- Add explicit `gc.collect()` and `torch.mps.empty_cache()` calls between phases in Python
- Set `OLLAMA_KEEP_ALIVE=0` environment variable to prevent Ollama from caching models between requests during attribution phase

**Warning signs:**
- macOS Activity Monitor showing "memory pressure" (yellow/red) during synthesis
- Swap usage above 4GB
- Generation throughput dropping below baseline (check chars/second metric)
- Any `mps backend out of memory` exception during synthesis that didn't occur at pipeline start

**Phase to address:**
Phase boundary between Attribution and Synthesis. Explicit teardown must be a first-class step in the pipeline orchestration.

---

## Moderate Pitfalls

### Pitfall 6: EPUB Structure Chaos — Non-Text Content Reaching the TTS

**What goes wrong:**
EPUB files are zipped HTML containers with no standardised structure. A naive parser will extract: cover page text, copyright notices, dedication pages, table of contents, chapter numbers as standalone items, footnotes, endnotes, embedded image alt-text, and front/back matter — all as if they were narrative prose. These reach the TTS pipeline and produce garbage audio segments that are interleaved with narrative.

**Why it happens:**
`ebooklib` returns all `ITEM_DOCUMENT` items without discrimination. BeautifulSoup `soup.get_text()` extracts everything in the DOM including nav elements. Different publishers structure EPUBs completely differently — there is no "chapter" standard.

**How to avoid:**
- Filter items by `spine` order (the EPUB spine defines reading order) rather than iterating all documents
- Strip known non-narrative elements: `<nav>`, `<aside>`, elements with class names matching `toc`, `footnote`, `copyright`, `dedication`
- Implement a minimum-word-count filter per extracted section (skip sections under 100 words)
- Run a "structure preview" step that prints extracted section count, word counts, and first 50 words of each — validate before running full pipeline
- Treat EPUB structure as an unknown on every new book; never assume structure will match a previous book

**Warning signs:**
- Extracted section list includes items titled "Copyright", "Dedication", "Also by", "Contents"
- Sections with fewer than 50 words appearing in the pipeline
- Duplicate text fragments (table of contents chapter titles re-appearing as standalone sections)

**Phase to address:**
Parse/Extract phase. The structure preview step should be mandatory before any LLM or TTS work begins.

---

### Pitfall 7: Quotation Mark Edge Cases Breaking Dialogue Detection

**What goes wrong:**
Dialogue detection via quotation marks fails on: (1) "smart quotes" vs. straight quotes — UTF-8 `\u201c`/`\u201d` vs. ASCII `"` — depending on EPUB encoding, (2) quotation marks used for non-dialogue purposes (scare quotes, titles, foreign words), (3) nested quotations where a character quotes another character, (4) British single-quote dialogue (`'He said, "yes",'`), (5) multi-paragraph dialogue where the opening quote appears without a closing quote at the paragraph end (standard typographic convention for continuing speech).

**Why it happens:**
Simple regex-based quote detection assumes dialogue == text-between-quotes. Fiction typography is significantly more complex. Multi-paragraph dialogue specifically — where only the final paragraph of a speech has a closing quote — is extremely common in genre fiction and will cause a regex matcher to either miss the continuation or grab everything until the next closing quote (eating narration).

**How to avoid:**
- Normalise all quotation mark variants to a canonical form before detection: map `\u2018`, `\u2019`, `\u201c`, `\u201d` and backtick variants to ASCII equivalents
- Handle multi-paragraph dialogue explicitly: a paragraph starting with `"` but not ending with `"` is a dialogue continuation
- Test the dialogue detector against 5 sample chapters from different publishers/genres before using it on real books
- Do not rely solely on quote detection — pass the LLM the full paragraph context including surrounding narration, which helps it identify dialogue even when punctuation is ambiguous

**Warning signs:**
- Long unbroken "dialogue" spans of 1000+ words (multi-paragraph dialogue being treated as one segment)
- Narrator voice being assigned to known dialogue lines (quotes misidentified as non-dialogue)
- Sections where no dialogue is detected despite the chapter being conversation-heavy

**Phase to address:**
Parse/Extract phase and LLM Attribution phase. Dialogue detection normalisation must happen in the parser; the LLM serves as a fallback and validator.

---

### Pitfall 8: Voice Reference Quality Mismatch from LibriTTS-P

**What goes wrong:**
LibriTTS-P contains 2,443 speakers, but speaker quality is highly variable. Some speakers have background noise, recording artefacts, inconsistent microphone distance, or strong regional accents that clash with the character being voiced. Selecting a reference based solely on gender/age metadata produces clones that sound wrong for the character, and once voice-character assignments are persisted to the checkpoint database, changing them requires re-synthesising all segments for that character.

**Why it happens:**
Reference datasets were curated for ASR/TTS training, not for audiobook character casting. The "best" speaker for a given character requires subjective evaluation. Automated matching (e.g., by pitch or speaking rate) cannot capture personality fit.

**How to avoid:**
- Build a voice preview tool before committing assignments: generate a 10-second test clip for each candidate reference voice using a fixed sample sentence
- Make voice-character assignments a separate, human-reviewable step before synthesis begins — not an automatic pipeline step
- Store voice assignments in the checkpoint database with a `confirmed` flag; only synthesise segments where the assignment is confirmed
- Select 3 candidate references per character, not 1 — compare them before locking in

**Warning signs:**
- Generated character voices that sound inconsistent with the character's described traits
- Voice clones with noticeable background noise or recording artefacts
- Characters with similar voices that listeners cannot distinguish

**Phase to address:**
Voice Matching phase. The assignment step must be interactive/reviewable, not fully automated.

---

### Pitfall 9: Checkpoint State Corruption from Interrupted Synthesis

**What goes wrong:**
A synthesis run interrupted mid-WAV-write (power loss, OOM kill, manual interrupt) leaves a partial WAV file on disk. The checkpoint database records the segment as "in-progress" or — worse — the interrupt happens after the DB write but before the file is fully flushed, leaving the DB claiming "complete" while the WAV is truncated. On resume, the pipeline skips the segment (DB says done) and assembles a chapter with a corrupt audio segment that plays as silence, noise, or truncated speech.

**Why it happens:**
WAV file writes and checkpoint DB updates are separate I/O operations. Without an atomic transaction spanning both, any interrupt between them creates inconsistency. This is particularly dangerous on macOS where unified memory pressure can trigger OOM kills with very short warning.

**How to avoid:**
- Write WAV to a `.tmp` path, then rename atomically to final path only after successful write and flush
- Update checkpoint DB only after the atomic rename succeeds
- On pipeline start/resume, validate all "complete" segments: verify the WAV file exists and is non-zero size and has a valid WAV header
- Treat any segment whose WAV is missing or malformed as "pending" regardless of DB state

**Warning signs:**
- WAV files with size of 0 bytes or size significantly smaller than neighbouring segments
- `wave` module raising `Error: file not recognised` on a segment that the DB marks complete
- Audio chapters with unexpected silence pockets or abrupt cuts

**Phase to address:**
Synthesis phase. Atomic write + validation logic must be part of the synthesis phase design, not an afterthought.

---

### Pitfall 10: Disk Space Exhaustion from WAV Intermediate Accumulation

**What goes wrong:**
A 300-page novel generates thousands of WAV segments. At 22kHz mono 16-bit, a 30-second segment is ~1.3MB. A 400-chapter-equivalent processing run (broken into 10,000+ segments) can accumulate 10–15GB of WAV intermediates before final MP3 assembly. On a development machine, this quietly fills the drive mid-run, causing synthesis to fail with a cryptic write error rather than a clear "disk full" message.

**Why it happens:**
Per-segment WAV intermediates are essential for checkpoint/resume but are rarely cleaned up eagerly. Developers focus on correctness and underestimate accumulation at scale. A standard novel at segment granularity can produce more data than expected.

**How to avoid:**
- Estimate storage requirements at pipeline start: `(total_segments * avg_segment_size_bytes)` printed as a human-readable size before beginning
- Implement chapter-level cleanup: after a chapter's WAV segments are assembled and verified, delete the individual segment WAVs
- Require minimum 5GB free disk space before starting any synthesis run; abort with a clear message if not available
- Keep the "assembled chapter" WAV until the final MP3 is verified, then delete

**Warning signs:**
- `OSError: [Errno 28] No space left on device` during synthesis
- Disk usage growing rapidly (monitor with `df -h` during long runs)
- `.wav` file count in the output directory exceeding 1000 files

**Phase to address:**
Synthesis phase and Assembly phase. Storage estimation at start; chapter-level cleanup as chapters complete.

---

## Minor Pitfalls

### Pitfall 11: Audio Sample Rate Mismatch on Assembly

**What goes wrong:**
Chatterbox outputs audio at its native sample rate (typically 24kHz or 22.05kHz). If different segments are generated with different effective rates (e.g., due to device/config changes between runs), concatenation via pydub produces subtle audio artefacts — speed variations, pitch shifts, or clicks at segment boundaries. The final MP3 output sounds correct to casual listening but fails quality checks.

**Prevention:**
Normalise all WAV segments to a canonical sample rate (24kHz) and mono channel immediately after generation, before writing to the checkpoint location. Use `pydub.AudioSegment.set_frame_rate()` and `set_channels()` as part of the post-synthesis step, not the assembly step.

---

### Pitfall 12: Character Name Variations Breaking the Registry

**What goes wrong:**
Fiction uses nicknames, titles, and epithets interchangeably for the same character ("Aragorn", "Strider", "the Ranger", "he"). The LLM may attribute lines to "the Ranger" which the character registry does not recognise, creating a new voice assignment for what is actually an existing character. The audiobook then has two voices for one character.

**Prevention:**
During Character Extraction phase, prompt the LLM explicitly to resolve aliases: "List all names, nicknames, titles, and epithets used for each character." Store the full alias list in the registry. Validate attribution results against the full alias list, not just canonical names.

---

### Pitfall 13: Silent Chatterbox Generation Producing Empty WAV

**What goes wrong:**
Chatterbox occasionally generates a valid WAV file containing only silence — no error is raised, the file is non-zero size, and the checkpoint records success. The audio chapter has pockets of silence that are indistinguishable from legitimate pauses until listened to.

**Prevention:**
After each segment generation, check RMS amplitude of the WAV. If RMS is below a threshold (e.g., -60dBFS), mark the segment as failed and regenerate. Use `pydub.AudioSegment.rms` for this check. Log all regeneration events.

---

### Pitfall 14: FFT Fallback Destroying MPS Performance

**What goes wrong:**
PyTorch's MPS backend falls back to CPU for unsupported FFT operations used in some audio processing paths. This is silent — no warning is logged — and MPS throughput drops to near-CPU levels. The developer assumes MPS is working because no error occurred.

**Prevention:**
Set `PYTORCH_ENABLE_MPS_FALLBACK=1` (this enables fallback without crashing) but also log a warning when it triggers. Benchmark a 10-segment test run and compare throughput against a known-good CPU baseline; investigate if MPS isn't at least 2x faster.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Skip voice preview, auto-assign LibriTTS voices | Faster initial run | Wrong voice for characters, costly re-synthesis | Never — review is cheap, re-synthesis is expensive |
| Process full chapters without chunking for LLM | Simpler code | Context window truncation, hallucinated attribution | Never |
| Use single global checkpoint DB without validation | Simple implementation | Corrupt resume state after crashes | Never for synthesis; OK for attribution which is fast to re-run |
| Skip EPUB structure preview | Faster first run | Garbage content (copyright, ToC) in pipeline | Never on first book; acceptable on a known-clean EPUB |
| Keep all WAV intermediates until end | Simpler cleanup logic | Disk exhaustion on long books | Only if drive has 50GB+ free |
| Hard-code character voice assignments | Avoids building preview tool | Locked into wrong voices with no easy re-cast | Never — always store assignments as data, not code |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Ollama API | Default 2048-token context for attribution | Set `num_ctx=32768` per request via Modelfile or API param |
| Ollama API | Assuming model is unloaded after attribution phase | Explicitly call `keep_alive=0` or `ollama stop`; verify with `ollama ps` |
| Chatterbox TTS | Passing full paragraphs (500+ chars) as single chunks | Pre-split to ≤280 chars at sentence boundaries before synthesis |
| Chatterbox MPS | Importing chatterbox without resolving PyTorch version conflict | Install PyTorch MPS first, then chatterbox deps manually |
| LibriTTS-P dataset | Downloading entire dataset (100GB+) for 2443 speakers | Pre-filter: download only `train-clean-360` subset; sample 3 speakers per demographic bucket |
| ebooklib | Iterating all `ITEM_DOCUMENT` items | Filter to spine order only; validate with word-count threshold |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| No MPS health check before long run | 8-hour run completes on CPU instead of MPS, 5x slower than expected | Benchmark test run of 10 segments; verify MPS device in use | Every run if MPS config is broken |
| LLM attribution on full book sequentially | Attribution takes hours on large books | Chunk chapters to 2000 words max; pipeline is sequential anyway but chunk size controls LLM throughput | Books over 100K words |
| No chapter-level WAV cleanup | Disk fills mid-synthesis | Chapter-complete cleanup hook | Books with 300+ segments (most novels) |
| Re-running attribution from scratch on resume | LLM attribution cost paid multiple times | Checkpoint attribution results per-segment in DB | Any interrupted run |
| Loading full LibriTTS-P index at startup | 10+ second startup time, 500MB+ RAM for index | Pre-build a filtered voice index (JSON) at setup time; load only that | First time developer ignores this |

---

## "Looks Done But Isn't" Checklist

- [ ] **Checkpoint resume:** Verify WAV files exist and are non-corrupt for all DB-marked-complete segments before trusting resume state
- [ ] **Voice assignments:** Confirm every character in the attribution results has a LibriTTS voice assigned before synthesis begins — not just the top N characters
- [ ] **Dialogue detection:** Validate on 3 different EPUBs with different publisher encodings before treating the parser as reliable
- [ ] **MPS acceleration:** Confirm MPS is actually in use (not silently falling back to CPU) by measuring throughput against CPU baseline
- [ ] **Character registry:** Confirm alias resolution is working — "the Captain" and "Captain Vimes" should resolve to the same character
- [ ] **Audio quality:** Spot-check 5 random segments per chapter for silence, truncation, or clipping before assembling the chapter
- [ ] **Ollama context:** Verify `num_ctx` is set to 32K+ for attribution runs; test with a known-long chapter that exceeds 4K tokens

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Chatterbox cutoff producing truncated audio | LOW | Re-chunk the offending segment to smaller pieces; re-synthesise only that segment |
| MPS instability causing corrupted segments | LOW | Set `PYTORCH_ENABLE_MPS_FALLBACK=1`; regenerate flagged segments on CPU |
| Ollama context truncation causing bad attribution | MEDIUM | Re-run attribution on the affected chapters with corrected `num_ctx`; regenerate only segments with attribution changes |
| Wrong voice assignments discovered late | HIGH | Re-synthesise all segments for the mis-assigned character; rebuild chapter audio |
| Checkpoint DB inconsistency after crash | MEDIUM | Run validation pass: compare DB state against filesystem; reset inconsistent segments to pending; re-run synthesis for those segments only |
| Disk exhaustion mid-synthesis | MEDIUM | Free space, validate existing segments, resume from last checkpoint; add chapter-level cleanup going forward |
| EPUB garbage content in pipeline | MEDIUM | Re-extract with improved structure filter; re-run attribution and synthesis for garbage segments |

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Chatterbox 40-second cutoff | Parse/Chunk phase | Assert no chunk > 280 chars before any synthesis call |
| Chatterbox MPS instability | Environment Setup + Synthesis phase | Run 10-segment benchmark; confirm MPS device; measure throughput |
| Ollama context truncation | Attribution phase | Log token estimate per request; test with known-long chapter |
| LLM misattribution / hallucination | Attribution phase + Character Extraction phase | Character registry validation; sanity-check unknown characters |
| Memory pressure / OOM crash | Phase boundary (Attribution → Synthesis) | `ollama stop` + `gc.collect()` + memory check before synthesis |
| EPUB structure chaos | Parse/Extract phase | Structure preview step; word-count filter; spine-order-only extraction |
| Quotation mark edge cases | Parse/Extract phase | Test on 5 EPUBs before treating parser as reliable |
| Voice reference quality mismatch | Voice Matching phase | Interactive preview step; `confirmed` flag before synthesis |
| Checkpoint corruption after crash | Synthesis phase | Atomic WAV write + resume validation pass |
| WAV disk space exhaustion | Synthesis phase + Assembly phase | Upfront storage estimate; chapter-level cleanup |
| Sample rate mismatch | Synthesis phase | Normalise to 24kHz immediately post-generation |
| Character name aliases | Character Extraction phase | Prompt LLM for full alias list; validate attribution against aliases |
| Silent WAV generation | Synthesis phase | RMS check after each segment; auto-regenerate below threshold |
| FFT MPS fallback | Environment Setup | Benchmark vs CPU baseline; alert if MPS is not faster |

---

## Sources

- Chatterbox 40-second cutoff: [GitHub Issue #76 — resemble-ai/chatterbox](https://github.com/resemble-ai/chatterbox/issues/76)
- Chatterbox Extended (character limit workaround): [petermg/Chatterbox-TTS-Extended](https://github.com/petermg/Chatterbox-TTS-Extended)
- Chatterbox MPS Apple Silicon instability: [Jimmi42/chatterbox-tts-apple-silicon-code — Hugging Face](https://huggingface.co/Jimmi42/chatterbox-tts-apple-silicon-code)
- Chatterbox TTS audiobook server with MPS notes: [devnen/Chatterbox-TTS-Server](https://github.com/devnen/Chatterbox-TTS-Server)
- Ollama context window defaults and configuration: [How to Increase Ollama's Context Window Size](https://www.arsturn.com/blog/how-to-increase-ollama-context-window-size)
- Ollama large context degradation: [GitHub Issue #9890 — ollama/ollama](https://github.com/ollama/ollama/issues/9890)
- LLM context rot research 2025: [Context Rot — Chroma Research](https://research.trychroma.com/context-rot)
- EPUB structure and extraction pitfalls: [ebook2audiobook — DrewThomasson](https://github.com/DrewThomasson/ebook2audiobook)
- Extracting text from EPUB in Python: [bitsgalore.org](https://bitsgalore.org/2023/03/09/extracting-text-from-epub-files-in-python.html)
- Dialogue/quotation detection in fiction (CoreNLP): [Stanford CoreNLP QuoteAnnotator](https://stanfordnlp.github.io/CoreNLP/quote.html)
- BookNLP quotation attribution: [Improving Automatic Quotation Attribution in Literary Novels](https://arxiv.org/html/2307.03734)
- PyTorch MPS SDPA memory issues: [Optimizing PyTorch MPS Attention](https://medium.com/@rakshekaraj/optimizing-pytorch-mps-attention-memory-efficient-large-sequence-processing-without-accuracy-5239f565f07b)
- Apple Silicon PyTorch MPS state 2025: [State of PyTorch Hardware Acceleration 2025](https://tunguz.github.io/PyTorch_Hardware_2025/)
- Voice cloning reference audio quality: [Best TTS API with Voice Cloning 2026 — Fish Audio](https://fish.audio/blog/best-text-to-speech-api-voice-cloning/)
- LibriTTS speaker quality variance: [LibriTTS paper — arxiv.org](https://arxiv.org/abs/1904.02882)
- Multi-voice TTS speaker identity drift: [Voice Cloning: Comprehensive Survey 2025](https://arxiv.org/pdf/2505.00579)
- Audiobook storage requirements (10-30GB recommendation): [Building audiobooks with XTTS-V2 — Medium](https://medium.com/@jaimonjk/building-audiobooks-using-the-open-source-xtts-v2-model-6bfbbd412fee)
- Common Ollama local LLM deployment mistakes: [Common mistakes in local LLM deployments — Medium](https://sebastianpdw.medium.com/common-mistakes-in-local-llm-deployments-03e7d574256b)
- Speaker attribution in fiction NLP challenges: [Improving Quotation Attribution with Fictional Character Embeddings](https://arxiv.org/html/2406.11368v1)

---
*Pitfalls research for: EPUB-to-multi-voice-audiobook pipeline (local Python, M4 Mac)*
*Researched: 2026-03-03*
