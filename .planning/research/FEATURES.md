# Feature Research: v1.1 Pipeline Quality Improvements

**Domain:** AI audiobook production pipeline (EPUB-to-audiobook, multi-voice)
**Researched:** 2026-03-04
**Confidence:** MEDIUM-HIGH (tech stack verified via official sources and community implementations; Qwen3-TTS emotion + voice cloning interaction is LOW confidence due to open limitations)

## Critical Discovery: Emotion + Voice Cloning Gap

Before categorizing features, a research-critical finding: **Qwen3-TTS Base model (voice cloning) does NOT support the `instruct` parameter for emotion control.** The instruction/emotion system only works with the CustomVoice model's 9 preset speakers (Ryan, Aiden, etc.), not with cloned voices from reference audio.

This means the planned three-layer emotion system cannot work as originally conceived with voice cloning. Workarounds exist (fine-tuning, VoiceDesign, text-inherent emotion from semantic understanding) but the "cloned voice + explicit emotion instruction" combination is an unsolved problem in the Qwen3-TTS ecosystem as of March 2026.

**Confidence:** HIGH -- confirmed via official GitHub discussions (#231, #238) and HuggingFace model card.

**Impact:** The emotion system design must be revised to work through text-semantic inference (automatic) + speech-act tag mapping (parameter tweaks) rather than explicit emotion instructions passed to the TTS engine.

---

## Feature Landscape

### Table Stakes (Baseline Quality for AI Audiobook)

Features that any audiobook pipeline must have. Missing these means the output sounds noticeably AI-generated or unprofessional.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Consistent volume/loudness across segments | Listeners notice jarring volume shifts immediately | LOW | Already implemented (LUFS -19.0 via pyloudnorm). Keep as-is. |
| No audio clicks/pops at segment boundaries | Clicks are the #1 "this sounds AI-generated" artifact | LOW | Not currently handled. Fade-in/fade-out at segment edges (5-10ms) eliminates this. Part of feature 8. |
| Correct speaker attribution | Wrong voice on a dialogue line breaks immersion completely | MEDIUM | Already implemented via Qwen3 8B. Feature 4 improves accuracy. |
| Distinct voices per character | Identical voices for different characters is confusing | MEDIUM | Already implemented via LibriTTS-P voice cloning. Feature 1 improves cloning quality. |
| Natural pause timing | Fixed-duration silence between every segment sounds robotic | LOW | Currently fixed values. Feature 7 adds randomization within ranges. |
| Accurate dialogue/narration detection | Misclassified narration as dialogue (or vice versa) puts wrong voice on text | MEDIUM | Currently regex-based. Feature 6 replaces with LLM. |
| Clean audio (no artifacts, noise, distortion) | Any non-speech audio is distracting in a long-form listen | MEDIUM | Feature 8 adds professional post-processing chain. |

### Differentiators (Quality Gap Closers Toward Professional Audiobook)

Features that close the gap between "functional AI audiobook" and "enjoyable multi-hour listen."

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Text-inherent emotional prosody (Qwen3-TTS) | Model infers emotion from text semantics -- "I hate you!" sounds angry without being told | HIGH (TTS swap) | The engine upgrade IS the differentiator. Qwen3-TTS deeply integrates text semantic understanding to adjust tone, rhythm, emotional expression automatically. |
| Longer, smoother segments (500-600 chars) | Fewer seam points = fewer voice drift opportunities, better prosody continuity | LOW (once TTS swapped) | Chatterbox hard limit ~300 chars. Qwen3-TTS handles much longer text. Reduces total segment count ~40-50%. |
| Voice consistency verification + regeneration | Detect segments where voice drifts from reference and regenerate them | HIGH | Novel for local pipelines. Uses speaker embeddings (Resemblyzer) for cosine similarity comparison against reference. |
| LLM-based dialogue detection with speech-act tagging | Tags spoken/thought/shouted/whispered -- goes beyond binary dialogue/narration | MEDIUM | No open-source audiobook tool does this. Feeds emotion mapping and synthesis parameter selection. |
| Professional mastering chain | EQ + compression + limiting brings output to ACX broadcast standard | MEDIUM | Spotify's pedalboard library provides studio-quality effects. Most competitors only normalize loudness. |
| Context-aware randomized pauses | Variable silence mimics human narrator's natural rhythm and cadence | LOW | Simple but impactful. Professional audiobooks vary pause timing by context. |

### Anti-Features (Commonly Desired, Actually Problematic for This Project)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Explicit per-line emotion instructions with cloned voices | "I want angry Harry, sad Hermione" | Base model ignores `instruct` param for cloned voices; fine-tuning required per voice; CustomVoice only has 9 presets | Rely on Qwen3-TTS text-semantic emotion inference. The model reads the text and infers emotion automatically. Supplement with speech-act tags mapped to synthesis parameters. |
| Real-time emotion slider/controls | Manual tuning per segment | 3000+ segments per book makes manual tuning impractical | Automated system with sensible defaults. Manual override only for flagged segments in future versions. |
| Multiple TTS engines for different character types | "Use engine A for female, engine B for male" | Memory constraints (16GB), voice consistency impossible across engines, doubles complexity | Single engine (Qwen3-TTS 1.7B) for all voices. Voice variety comes from reference audio diversity in LibriTTS-P (2,443 speakers). |
| De-essing as default post-processing | "Remove sibilance like pro audio" | ACX explicitly warns against de-essing -- it often does more harm than good with synthetic speech. TTS rarely has the same sibilance issues as microphone recordings. | Omit de-essing. Apply manually only if specific voices exhibit sibilance in listening tests. |
| Ultra-long reference clips (30+ seconds) | "More reference = better clone" | Quality plateaus at 10-15s and degrades beyond. >30s clips cause generation hangs in Qwen3-TTS. | Target 10-15s clean reference clips with SNR filtering. |
| Inline emotion tag markup per sentence | "Tag each sentence with (angry) or (sad)" | Qwen3-TTS lacks reliable mid-paragraph emotion switching (GitHub discussion #238). Structured tags are a feature request, not a capability. | Rely on per-segment text semantics. Split scenes with strong emotion shifts into separate segments naturally at sentence boundaries. |

---

## The 9 Target Features: Detailed Analysis

### Feature 1: Qwen3-TTS 1.7B Swap (Replacing Chatterbox)

**Category:** Differentiator (foundational -- everything else depends on this)
**Complexity:** HIGH
**Priority:** P1

**What it does:** Replaces Chatterbox TTS engine (PyTorch, MPS, ~300 char limit, exaggeration/cfg_weight params) with Qwen3-TTS 1.7B Base model via mlx-audio (Apple Silicon native via MLX, ~32K token context, 3s minimum voice cloning, text-semantic emotion).

**Expected behavior:**
- Load `Qwen3-TTS-12Hz-1.7B-Base` (8-bit quantized) via `mlx_audio.tts.utils.load_model()`
- Voice cloning: `generate(text=..., ref_audio=..., ref_text=..., lang_code="English")`
- Reference audio: provide both the WAV file AND a transcript for best cloning fidelity
- Output: audio as `mx.array`, convert to WAV via soundfile or similar
- Throughput: ~1000 chars/minute on M2 (M4 should be faster)
- Memory: 1.7B 8-bit ~= 2-4GB model weight. Fits in 16GB when Ollama is unloaded.
- Long-form: stable synthesis exceeding 10 minutes. Handles chunking internally for voice cloning mode.

**Key differences from Chatterbox:**

| Aspect | Chatterbox | Qwen3-TTS Base |
|--------|-----------|----------------|
| Framework | PyTorch (MPS with fallback) | MLX (Apple Silicon native) |
| Char limit | ~300 hard limit | ~32K tokens (effectively unlimited for segments) |
| Emotion control | `exaggeration` float param | Text-semantic inference (automatic) |
| Voice cloning input | `audio_prompt_path` (WAV only) | `ref_audio` + `ref_text` (WAV + transcript) |
| Min reference length | ~5 seconds | 3 seconds |
| Sample rate | Model-dependent | 12Hz token rate, reconstructed to audio |
| MPS setup | Manual component migration, CPU fallback | Not needed (MLX handles Metal natively) |

**Verified via:** Official Qwen3-TTS repo (HIGH), mlx-audio README (HIGH), HuggingFace model card (HIGH), technical report arxiv 2601.15621 (HIGH).

---

### Feature 2: Larger Chunk Sizes (500-600 chars)

**Category:** Differentiator (prosody quality)
**Complexity:** LOW (once feature 1 lands)
**Priority:** P1 (ships with TTS swap)

**What it does:** Increases `CHAR_LIMIT` in `segmenter.py` from 280 to 500-600 characters.

**Expected behavior:**
- Fewer segments per book (~40-50% reduction)
- Better intra-sentence prosody (no mid-sentence splits)
- Faster total synthesis time (fewer calls, less overhead)
- The Qwen3-Audiobook-Converter project defaults to 1200-word chunks, suggesting much larger is viable
- Start at 500 chars, test quality, potentially increase

**Risks:**
- Very long segments may cause voice drift within a single generation
- Need empirical testing to find the sweet spot
- Sentence boundary splitting logic remains important -- just with a higher ceiling

**Dependency:** Requires feature 1 (Chatterbox has hard ~300 char limit).

---

### Feature 3: Longer Voice References (REVISED: 10-15s, not 20-30s)

**Category:** Table stakes improvement
**Complexity:** LOW
**Priority:** P1 (ships with TTS swap)

**REVISED TARGET: 10-15 seconds, not 20-30 seconds.** Research conclusively shows quality scales linearly from 3 to 15 seconds, then plateaus and eventually degrades. The Qwen3-TTS ecosystem warns that clips >30s cause generation hangs. The `ref_audio_max_seconds` parameter defaults to 30s as a safety cap, not a target.

**What it does:** Updates `clip_selector.py` to:
1. Select reference clips in the 10-15 second duration range (not just longest)
2. Apply SNR (signal-to-noise ratio) filtering to reject noisy clips
3. Provide transcript of reference audio (`ref_text` parameter) for improved cloning
4. Optionally concatenate shorter clips from the same speaker to reach target duration

**Implementation notes:**
- LibriTTS-R includes transcripts in `.normalized.txt` files alongside each WAV
- Current selector picks longest clip (by file size proxy) -- change to target 10-15s range
- At 24kHz mono 16-bit, 10s = 480KB, 15s = 720KB -- use these as size range targets
- SNR estimation: measure RMS of silence segments vs speech segments

**Dependency:** Requires feature 1 (`ref_text` parameter is Qwen3-TTS specific).

---

### Feature 4: LLM Model Upgrade for Attribution

**Category:** Table stakes improvement
**Complexity:** LOW
**Priority:** P2 (independent of TTS swap)

**What it does:** Upgrades Ollama LLM from `qwen3:8b` Q4_K_M to either `qwen3:14b` Q4_K_M or `qwen3:8b` Q8_0 for better attribution accuracy.

**Expected behavior:**
- `qwen3:14b` Q4_K_M: ~9GB VRAM, better reasoning, ~2x slower
- `qwen3:8b` Q8_0: ~8.5GB VRAM, same architecture but fewer quantization artifacts
- Either fits in 16GB when TTS is not running (sequential phase design)
- Attribution prompts unchanged -- same structured output format
- Expect 5-15% reduction in low-confidence attributions

**Recommendation:** Start with `qwen3:8b` Q8_0 (easiest swap, measurable improvement, minimal speed impact). Move to 14b if attribution errors are still problematic after testing.

**Dependency:** Independent. Can ship before, with, or after TTS swap.

---

### Feature 5: Three-Layer Emotion System (REVISED DESIGN)

**Category:** Differentiator
**Complexity:** HIGH
**Priority:** P2 (depends on features 1 and 6)

**Original design:** Character baseline + scene mood + line overrides via `instruct` parameter.

**REVISED design (given Base model limitation):** The emotion system must work through three mechanisms that do NOT use the `instruct` parameter:

**Layer 1 -- Text-Semantic Emotion (automatic, no code needed):**
Qwen3-TTS automatically infers emotion from text content. "I hate you!" sounds angry. "She whispered softly" sounds gentle. This is the primary emotion channel and works with voice cloning out of the box. The model "adaptively adjusts tone, rhythm, and emotional expression based on text semantics." This layer is FREE -- it comes with feature 1.

**Layer 2 -- Speech-Act Tag Mapping (from feature 6):**
When the LLM dialogue detector tags a line as whispered/shouted/thought:
- **Whispered:** Post-process with volume reduction + slight high-frequency boost, or prepend contextual text cue
- **Shouted:** Post-process with slight volume boost + compression
- **Thought/internal monologue:** Route to narrator voice instead of character voice (already partially handled -- narration goes to narrator)
- **Spoken (default):** No modification

**Layer 3 -- Scene Context via Text (text modification):**
For narration segments, the LLM can be prompted to detect scene mood and prepend brief context markers. Example: in a tense confrontation scene, surrounding narration text ("He snarled", "she snapped") already primes the model. For ambiguous scenes, inject subtle text cues.

**Expected behavior:**
- No explicit emotion instructions passed to TTS engine
- Emotion comes from: text semantics (inherent) + speech-act tags (mapped to post-processing) + text-level context
- Quality improvement is subtle but cumulative over 3000+ segments
- Whispered text genuinely sounds softer; shouted text has more energy

**Dependency:** Feature 1 (Qwen3-TTS semantic understanding) + Feature 6 (speech-act tags). Layer 1 is effectively free once Qwen3-TTS is integrated.

---

### Feature 6: LLM-Based Dialogue Detection

**Category:** Table stakes improvement + Differentiator
**Complexity:** MEDIUM
**Priority:** P2

**What it does:** Replaces regex-based dialogue detection in `segmenter.py` with LLM classification that also tags speech acts.

**Expected behavior:**
- LLM receives paragraph text + surrounding context (2 paragraphs before/after)
- Returns per-segment: `type` (dialogue/narration/scene_break) + `speech_act` (spoken/thought/shouted/whispered/narrated)
- Handles edge cases regex misses:
  - Indirect speech ("She told him she was leaving")
  - Mixed dialogue + narration paragraphs
  - Unquoted dialogue (common in literary fiction)
  - Multi-paragraph dialogue spanning quote boundaries
  - Internal monologue without quotes
- Speech-act tags feed feature 5's emotion mapping

**Implementation approach:**
- Run as part of Phase 2 (LLM is already loaded for attribution)
- Can be a pre-pass before attribution: detect dialogue type first, then attribute speakers
- Use structured output (same Pydantic pattern as existing `ChapterAttributionResult`)
- Cache results per chapter for incremental re-runs (same pattern as attribution cache)
- Batch process per chapter to minimize LLM calls

**Trade-offs:**
- LLM calls are slower than regex (~seconds vs microseconds per chapter)
- But runs once and caches; wall-time impact is modest (attribution already takes minutes per chapter)
- Accuracy improvement is significant for books with non-standard quoting conventions

**Dependency:** Feature 4 (better LLM) improves detection quality. Feature 5 (emotion) consumes speech-act tags.

---

### Feature 7: Randomized Pause Timing

**Category:** Table stakes
**Complexity:** LOW
**Priority:** P2 (independent)

**What it does:** Replaces fixed silence durations in `concatenator.py` with randomized values within context-aware ranges.

**Expected behavior:**

| Boundary Type | Current (fixed) | Proposed (range) |
|--------------|-----------------|------------------|
| Sentence | 400ms | 300-500ms |
| Paragraph | 900ms | 700-1100ms |
| Scene break | 2500ms | 2000-3000ms |
| Chapter transition | 1500ms | 1200-1800ms |
| Speaker change (NEW) | N/A | 500-800ms |
| Post-question (NEW) | N/A | +100-200ms extra |

**Implementation:**
- Modify `_get_silence_ms()` in `concatenator.py` to use `random.uniform(min, max)`
- Add speaker change detection (compare `speaker` field of current vs previous segment)
- Add punctuation-aware pauses (check last character of previous segment text)
- Optional: accept a `seed` parameter for reproducible output

**Dependency:** Independent. Can be implemented at any time. Works with current or new TTS engine.

---

### Feature 8: Post-Processing Pipeline

**Category:** Differentiator
**Complexity:** MEDIUM
**Priority:** P3

**What it does:** Adds a professional mastering chain for ACX-grade output quality.

**Segment-level processing (before concatenation):**

| Step | Tool | Purpose |
|------|------|---------|
| Silence trim | pydub `detect_leading_silence` | Remove leading/trailing silence from each WAV |
| Click removal | pydub fade (5-10ms) | Fade-in/fade-out at segment edges to eliminate concatenation pops |
| Sample rate normalize | pydub `set_frame_rate` | Ensure all segments match (e.g., 24kHz mono) before concatenation |

**Chapter-level processing (after concatenation, before MP3 export):**

| Step | Tool | Purpose | Settings |
|------|------|---------|----------|
| High-pass filter | pedalboard `HighpassFilter` | Remove low-frequency rumble | 80Hz cutoff |
| Light compression | pedalboard `Compressor` | Even out dynamics | 2:1 ratio, -20dB threshold |
| LUFS normalization | pyloudnorm (existing) | Target loudness | -19.0 LUFS (keep current) |
| Limiter | pedalboard `Limiter` | Prevent clipping | -3.1dB ceiling |
| Export upgrade | pydub/ffmpeg | Better bitrate | 44.1kHz 192kbps CBR MP3 |

**Processing order is critical:** High-pass -> Compression -> Normalization -> Limiting. This matches the professional audiobook mastering chain (EQ -> dynamics -> loudness -> ceiling).

**ACX standard requirements (for reference quality target):**
- Peak: no louder than -3dB
- RMS: between -18dB and -23dB
- Noise floor: below -60dB

**Tool recommendation:** Spotify's `pedalboard` library -- 300x faster than pySoX, studio-quality effects, releases GIL for multi-core processing, battle-tested at Spotify scale. Already has Compressor, Limiter, HighpassFilter, LowpassFilter, Gain, and Reverb. Installs with `pip install pedalboard`.

**Dependency:** Independent of TTS swap. Can be applied to existing Chatterbox output for immediate quality improvement.

---

### Feature 9: Voice Consistency Pass

**Category:** Differentiator (novel for local pipelines)
**Complexity:** HIGH
**Priority:** P3

**What it does:** After synthesis, compare each segment's voice embedding against the reference clip embedding. Flag and regenerate segments where voice has drifted.

**Expected behavior:**
1. Extract speaker embedding from each character's reference clip (once per character)
2. Extract speaker embedding from each synthesized WAV segment
3. Compute cosine similarity between segment embedding and reference embedding
4. Flag segments below threshold (e.g., cosine similarity < 0.75)
5. Regenerate flagged segments (same text, same reference, different random seed)
6. Re-check after regeneration; accept best attempt across all tries
7. Maximum 3 regeneration attempts per segment to avoid infinite loops

**Tool recommendation:** Resemblyzer (`pip install resemblyzer`). Produces 256-dim GE2E speaker embeddings. Lightweight, CPU-only (PyTorch-based but small model). Reliable for audio >= 2.6 seconds. Alternative: SpeechBrain ECAPA-TDNN (more accurate but heavier).

**Key considerations:**
- Minimum audio duration for reliable embedding: ~2.6 seconds
- Skip consistency check for segments < 3 seconds (embedding unstable for short audio)
- Cosine similarity threshold needs empirical tuning -- start at 0.75
- Each character needs a reference embedding computed once from their reference clip
- Regeneration uses a different random seed each attempt
- Report: "X of Y segments flagged, Z regenerated successfully"

**Memory note:** Resemblyzer's voice encoder is small (~17MB). Can coexist with Qwen3-TTS in 16GB memory.

**Dependency:** Should run after feature 1 is stable. Voice consistency is different between Chatterbox and Qwen3-TTS, so tuning the threshold after the swap makes sense.

---

## Feature Dependencies

```
Feature 1: Qwen3-TTS Swap (FOUNDATION)
    |
    +-- Feature 2: Larger Chunks (trivial CHAR_LIMIT change once TTS swapped)
    |
    +-- Feature 3: Longer References (ref_text param is Qwen3-TTS specific)
    |
    +-- Feature 5: Emotion System (needs Qwen3-TTS semantic inference)
    |       |
    |       +-- requires Feature 6: LLM Dialogue Detection (speech-act tags)
    |
    +-- Feature 9: Voice Consistency Pass (embeddings + regeneration)

Feature 4: LLM Upgrade (INDEPENDENT)
    |
    +-- enhances Feature 6: LLM Dialogue Detection

Feature 6: LLM Dialogue Detection
    |
    +-- feeds Feature 5: Emotion System (speech-act tags)

Feature 7: Randomized Pauses (INDEPENDENT)

Feature 8: Post-Processing Pipeline (INDEPENDENT)
```

### Dependency Notes

- **Feature 1 is the critical path.** Features 2, 3, 5, 9 all depend on it directly. Must be validated first.
- **Features 2 and 3 ship WITH feature 1** -- they are trivial changes once the TTS engine is swapped (constant change and clip selector update).
- **Feature 4 is fully independent** -- can ship in any order. Even before the TTS swap.
- **Features 7 and 8 are independent** -- can be applied to current Chatterbox output today.
- **Feature 5 depends on both Feature 1 AND Feature 6** -- Layer 1 (text-semantic) comes free with Qwen3-TTS. Layers 2 and 3 need speech-act tags from LLM dialogue detection.
- **Feature 9 should be last** -- it validates and fixes output from all other features. No point tuning consistency thresholds until TTS engine and emotion system are stable.

---

## Implementation Priority Order

### Phase A: Foundation (TTS Engine Swap)

| Feature | Rationale |
|---------|-----------|
| 1. Qwen3-TTS Swap | Everything depends on this. Validate output quality, establish new baseline. |
| 2. Larger Chunks | Ships with feature 1 -- just a constant change in segmenter.py. |
| 3. Longer References | Ships with feature 1 -- clip selector update + ref_text support. |

### Phase B: Intelligence (LLM Improvements)

| Feature | Rationale |
|---------|-----------|
| 4. LLM Upgrade | Independent easy win. Better attribution accuracy. |
| 6. LLM Dialogue Detection | Replaces regex. Adds speech-act tags. LLM already loaded for Phase 2. |
| 5. Emotion System | Builds on Qwen3-TTS semantic inference + speech-act tags from feature 6. |

### Phase C: Polish (Professional Quality)

| Feature | Rationale |
|---------|-----------|
| 7. Randomized Pauses | Simple, high-impact naturalness improvement. |
| 8. Post-Processing Pipeline | Mastering chain for ACX-grade output. |
| 9. Voice Consistency Pass | Final quality gate. Detect and fix drift after everything else is stable. |

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Risk | Priority |
|---------|------------|---------------------|------|----------|
| 1. Qwen3-TTS Swap | HIGH | HIGH | MEDIUM (new engine, new API, new failure modes) | P1 |
| 2. Larger Chunks | HIGH | LOW | LOW (constant change) | P1 |
| 3. Longer References | MEDIUM | LOW | LOW (clip selection logic) | P1 |
| 4. LLM Upgrade | MEDIUM | LOW | LOW (Ollama model swap) | P2 |
| 5. Emotion System | HIGH | HIGH | HIGH (cloned voice + emotion gap) | P2 |
| 6. LLM Dialogue Detection | MEDIUM | MEDIUM | LOW (established LLM pattern) | P2 |
| 7. Randomized Pauses | MEDIUM | LOW | LOW (simple randomization) | P2 |
| 8. Post-Processing | HIGH | MEDIUM | LOW (pedalboard is battle-tested) | P3 |
| 9. Voice Consistency | MEDIUM | HIGH | MEDIUM (threshold tuning, regen loops) | P3 |

---

## Competitor Feature Analysis (v1.1 Features)

| Feature | tts-audiobook-tool | Qwen3-Audiobook-Converter | ElevenLabs | Our v1.1 Approach |
|---------|-------------------|--------------------------|------------|-------------------|
| TTS engine | 9 models (Qwen3, Chatterbox, etc) | Qwen3 (API or local) | Proprietary V3 | Qwen3-TTS 1.7B Base via MLX |
| Multi-voice | Yes (manual assignment) | No (single voice) | Yes (API, manual) | Yes (LLM-attributed, automated) |
| Voice cloning | Yes (per-model) | Yes (Qwen3 Base) | Yes (API) | Yes (LibriTTS-P + Qwen3 Base) |
| Emotion control | No explicit | No explicit | 50+ style/emotion tags | Text-semantic (auto) + speech-act mapping |
| Dialogue detection | No (manual) | No (sequential text) | No (manual) | LLM-based with speech-act tagging |
| Voice consistency | Whisper STT error detection | No | Proprietary | Embedding-based drift detection + regen |
| Post-processing | Loudness normalization | Basic concat | Proprietary mastering | Full chain (EQ, compression, limiting) |
| Pause control | Semantic-aware caesuras | No control | SSML break tags | Randomized context-aware ranges |
| Chunking | Paragraph/sentence-aware | 1200-word default | Automatic | Sentence-boundary-aware, 500-600 chars |
| Fully local | Yes | Partial (API option) | No (cloud only) | Yes |

**Our differentiators vs open-source competitors:**
- LLM-based dialogue detection with speech-act tagging (no competitor does this)
- Embedding-based voice consistency verification with regeneration (tts-audiobook-tool uses Whisper for text accuracy, not voice similarity)
- Full professional mastering chain (most competitors only normalize loudness)
- Integrated multi-voice pipeline with automated LLM attribution (most are single-voice or require manual assignment)

---

## Sources

- [Qwen3-TTS Official Repository](https://github.com/QwenLM/Qwen3-TTS) -- model variants, API, capabilities (HIGH confidence)
- [Qwen3-TTS Technical Report](https://arxiv.org/html/2601.15621v1) -- architecture, benchmarks, 32K token context (HIGH confidence)
- [mlx-audio Qwen3-TTS README](https://github.com/Blaizzy/mlx-audio/blob/main/mlx_audio/tts/models/qwen3_tts/README.md) -- MLX API, batch generation, Apple Silicon (HIGH confidence)
- [Qwen3-TTS CustomVoice HuggingFace](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice) -- emotion instruction format, 9 preset speakers (HIGH confidence)
- [Emotion in Cloned Voices Discussion #231](https://github.com/QwenLM/Qwen3-TTS/discussions/231) -- Base model ignores instruct param (HIGH confidence)
- [Inline Emotion Tags Discussion #238](https://github.com/QwenLM/Qwen3-TTS/discussions/238) -- per-line emotion control is a feature request, not a capability (HIGH confidence)
- [Qwen3-Audiobook-Converter](https://github.com/WhiskeyCoder/Qwen3-Audiobook-Converter) -- 1200-word chunk default, voice cloning chunking (MEDIUM confidence)
- [tts-audiobook-tool](https://github.com/zeropointnine/tts-audiobook-tool) -- competitor features, Whisper validation, semantic pauses (MEDIUM confidence)
- [mlx-audio on macOS Blog](https://mybyways.com/blog/qwen3-tts-with-mlx-audio-on-macos) -- API usage patterns, ~1000 chars/min, memory notes (MEDIUM confidence)
- [Qwen3-TTS Voice Cloning Guide](https://ocdevel.com/blog/20260302-qwen-tts-voice-cloning) -- 10-15s optimal reference, >30s causes hangs (MEDIUM confidence)
- [Spotify Pedalboard](https://github.com/spotify/pedalboard) -- Compressor, Limiter, HighpassFilter, 300x faster than pySoX (HIGH confidence)
- [Resemblyzer](https://github.com/resemble-ai/Resemblyzer) -- 256-dim GE2E speaker embeddings, cosine similarity (HIGH confidence)
- [ACX Audio Specs 2025-2026](https://narrationbox.com/blog/acx-audio-specs-explained-2025-2026) -- peak -3dB, RMS -18 to -23dB, noise -60dB (HIGH confidence)
- [Audacity Audiobook Mastering](https://support.audacityteam.org/audio-editing/audiobook-mastering) -- EQ -> Compression -> Limiting order (MEDIUM confidence)
- [Resemblyzer Effectiveness Study 2025](https://periodicals.karazin.ua/mia/article/view/28479) -- minimum 2.63s for reliable embeddings (MEDIUM confidence)
- [Qwen3-TTS Complete Guide (DEV Community)](https://dev.to/czmilo/qwen3-tts-the-complete-2026-guide-to-open-source-voice-cloning-and-ai-speech-generation-1in6) -- ecosystem overview, 10-15s reference sweet spot (MEDIUM confidence)

---
*Feature research for: v1.1 pipeline quality improvements*
*Researched: 2026-03-04*
