# Project Research Summary

**Project:** audio-book-plz v1.1
**Domain:** EPUB-to-audiobook pipeline — multi-voice, local, Apple Silicon (v1.1 quality improvements)
**Researched:** 2026-03-04
**Confidence:** MEDIUM (stack additions are young; emotion + voice-cloning gap is a confirmed architectural blocker)

## Executive Summary

audio-book-plz v1.1 is a 9-feature quality upgrade to an existing, working EPUB-to-audiobook pipeline. The central change is replacing Chatterbox TTS (PyTorch/MPS, ~300 char limit, memory-leaky) with Qwen3-TTS 1.7B via mlx-audio (Apple Silicon native MLX framework, ~32K token context, text-semantic emotion inference). This engine swap is the critical path: six of the nine features depend on it, and two more benefit from it. The architecture expands from 5 sequential phases to 7, inserting a dedicated Emotion Analysis phase (Phase 3) and a Voice Consistency Verification phase (Phase 6). The existing disk-based inter-phase contract, sequential LLM-then-TTS memory boundary, and checkpoint/resume pattern all remain intact and unchanged.

The recommended build order is three clearly sequenced groups. First: the TTS engine swap (Features 1, 2, 3) as an atomic unit — this is the highest-risk change and must be validated before anything builds on it. Second: the LLM intelligence upgrades (Features 4, 6, 5) which share the existing Ollama lifecycle and improve upstream data quality. Third: the production finishing layer (Features 7, 8, 9) which are self-contained assembly enhancements and a final quality gate. Each group provides independent validation and rollback points.

The single biggest technical risk is the confirmed Qwen3-TTS emotion + voice-cloning gap: the Base model (which supports voice cloning from reference audio) does NOT support the `instruct` emotion parameter. As of March 2026, explicit emotion control only works with the CustomVoice model's 9 preset speakers — not with cloned voices from reference audio. This is confirmed via official GitHub discussions #231 and #238. The planned three-layer emotion system must be redesigned to work through text-semantic inference (automatic, free with Qwen3-TTS) and speech-act tag post-processing rather than TTS emotion instructions. This is a capability reduction from the original conception but remains a meaningful improvement over v1.0's zero emotion awareness.

## Key Findings

### Recommended Stack

The stack change is surgical: remove `chatterbox-tts` and its PyTorch/MPS overhead, add `mlx`, `mlx-audio[tts]`, `pedalboard`, and `resemblyzer`. All v1.0 dependencies (Python 3.11, pydub, pyloudnorm, mutagen, sentence-transformers, Ollama client, typer, rich, pydantic, ebooklib, beautifulsoup4, lxml) stay unchanged. The Ollama model upgrades from `qwen3:8b` Q4_K_M to `qwen3:14b` Q4_K_M — a config constant change, not a code change. PyTorch remains as a transitive dependency of `sentence-transformers` and `resemblyzer` but is no longer explicitly imported or managed for TTS inference.

Memory budget on 16GB M4 is workable throughout. LLM phases (1-4, Ollama qwen3:14b Q4_K_M) use ~10GB — tight but fits with `OLLAMA_KV_CACHE_TYPE=q8_0`. TTS synthesis (Qwen3-TTS 1.7B 8-bit via MLX) uses ~3-4GB — notably lighter than Chatterbox's ~5-6GB. The strict sequential boundary (unload Ollama before loading TTS) remains the architecture's fundamental memory constraint and is unchanged from v1.0.

**Core technologies:**
- `mlx>=0.31.0` + `mlx-audio[tts]>=0.3.1`: TTS inference — Apple Silicon native, no PyTorch for inference, replaces Chatterbox. Primary model: `mlx-community/Qwen3-TTS-12Hz-1.7B-CustomVoice-8bit`.
- `pedalboard>=0.9.22`: Audio post-processing — Spotify's C++-backed professional effects chain (Compressor, HighpassFilter, Limiter, NoiseGate). GPLv3, acceptable for personal-use local tool.
- `resemblyzer>=0.1.3`: Voice consistency verification — 256-dim GE2E speaker embeddings, CPU-only, ~17MB model. Sufficient accuracy for same-model drift detection.
- Ollama `qwen3:14b-q4_K_M`: LLM upgrade — significantly better nuanced reasoning than 8B at same memory envelope with KV cache quantization.
- LibriTTS-R (data, not pip): Higher-quality reference clips with bundled `.normalized.txt` transcripts. Target 10-15 second clips (quality plateaus beyond 15s, generation hangs above ~30s).

### Expected Features

**Must have (table stakes — any audiobook pipeline needs these):**
- Consistent volume/loudness across segments (already in v1.0 via pyloudnorm LUFS -19.0)
- No audio clicks/pops at segment boundaries (5-10ms fade-in/fade-out — not yet implemented)
- Correct speaker attribution (improved via LLM upgrade to 14B)
- Distinct voices per character (improved via longer, SNR-filtered reference clips with transcripts)
- Natural pause timing (randomized within context-aware ranges, not fixed values)
- Accurate dialogue/narration detection (LLM-based with speech-act subtype tagging)
- Clean audio output (professional mastering chain via pedalboard)

**Should have (differentiators that close the gap to professional quality):**
- Text-inherent emotional prosody (Qwen3-TTS reads text semantics automatically — free with Feature 1)
- Longer, smoother TTS segments (500-600 chars vs 280 — reduces segment count ~40-50%)
- Voice consistency verification and regeneration (embedding-based drift detection)
- LLM-based dialogue detection with speech-act tagging (spoken/thought/shouted/whispered)
- Professional ACX-grade mastering chain (EQ + compression + limiting via pedalboard)
- Context-aware randomized pause timing

**Defer (v2+ or later iteration):**
- Explicit per-line emotion instructions with cloned voices — Base model ignores `instruct`; requires fine-tuning or upstream capability improvement
- Real-time emotion slider controls — impractical at 3000+ segments per book
- Multiple TTS engines per character type — memory and voice consistency constraints prohibit
- De-essing as default post-processing — ACX warns against it for synthetic speech
- Ultra-long reference clips (30+ seconds) — quality degrades, generation hangs
- Per-sentence inline emotion tag markup — Qwen3-TTS does not support this

### Architecture Approach

The existing 5-phase disk-based sequential pipeline expands to 7 phases by inserting Emotion Analysis (Phase 3, between Attribution and Voice Matching) and Voice Consistency Verification (Phase 6, between Synthesis and Assembly). A single Ollama model load now spans all four LLM-dependent phases (Parse, Attribute, Emotion, Match) before one explicit unload at the Phase 4-to-5 boundary — eliminating the per-phase load/unload cycles of v1.0. All inter-phase communication remains JSON on disk. Per-segment WAV intermediates in `wavs/ch{NN}/` are unchanged. Late imports for heavy dependencies (MLX, SpeechBrain) remain the established pattern.

**Major components:**
1. `src/parser/` (modify) — EPUB parsing + new LLM-based dialogue subtype detection
2. `src/attribution/extractor.py` (extend) — character extraction with emotion baseline fields
3. `src/emotion/` (NEW module) — scene mood analysis + line-level emotion overrides producing `emotions.json`
4. `src/matching/clip_selector.py` (rewrite) — 10-15s SNR-filtered reference clips with transcripts
5. `src/synthesis/tts_engine.py` (rewrite) — Qwen3-TTS via mlx-audio, replacing Chatterbox entirely
6. `src/verify/` (NEW module) — speaker embedding comparison and conditional regeneration
7. `src/assembly/postprocessor.py` (NEW file) — pedalboard effects chain (trim, gate, compress, EQ)
8. `src/assembly/concatenator.py` (modify) — Gaussian-randomized pause timing, crossfades
9. `src/pipeline.py` (modify) — orchestrate 7 phases, single Ollama load lifecycle

### Critical Pitfalls

1. **MLX Metal cache accumulation kills overnight synthesis runs** — `mx.metal.clear_cache()` must replace `torch.mps.empty_cache()` in `TTSEngine.cleanup_memory()` on day one of the TTS swap. Call every 10 segments. Set `mx.metal.set_cache_limit(4GB)`. Failure mode is progressive slowdown to swap thrashing over a full-book run.

2. **Emotion + voice cloning are mutually exclusive in Qwen3-TTS** — Confirmed (GitHub #231, #238): Base model (voice cloning from reference audio) ignores the `instruct` emotion parameter. CustomVoice model supports emotion but uses 9 preset speakers only — no custom voice cloning. Do NOT design the emotion system to pass emotion prompts to cloned voices; they will be silently ignored.

3. **Breaking the working pipeline during the TTS engine swap** — Implement Qwen3-TTS as a new class alongside Chatterbox, gated by a config flag. Keep Chatterbox working until Qwen3-TTS passes A/B quality comparison on 10+ segments. Old checkpoints must be gracefully invalidated (add engine version field), not silently reused.

4. **Ollama 14B causes swap thrashing if not fully unloaded before TTS** — 14B Q4_K_M uses ~10GB. Verify `ensure_ollama_unloaded()` actually frees memory (add sleep + memory check), not just sends the unload signal. Fallback is 8B Q8_0 (~8GB) if 14B proves unstable.

5. **Voice consistency pass creates infinite regeneration loops** — TTS variance naturally produces cosine similarity of 0.70-0.90 for the same speaker. A threshold above 0.80 will flag 20-30% of legitimate segments. Start at 0.60, cap regeneration at 3 attempts per segment, accept best result. If >15% of a character's segments are flagged, the problem is the reference clip, not the segments.

6. **Post-processing that degrades audio quality** — TTS audio already lacks human imperfections; removing more makes it sound robotic. Compression fights the emotion system's dynamic range. Apply the Hippocratic principle: each processing step requires A/B validation before commitment. Start with LUFS normalization only (v1.0 already has this), add one step at a time.

## Implications for Roadmap

The 9 features naturally cluster into three phases with clear dependency ordering. Feature research, architecture, and pitfalls all converge on the same groupings independently.

### Phase A: TTS Engine Swap (Features 1, 2, 3)

**Rationale:** Feature 1 (Qwen3-TTS swap) is the critical path. Features 2 (larger chunks) and 3 (longer references with transcripts) ship with it because they are trivial changes once the engine is in place AND Feature 3 is a prerequisite for Feature 1 to achieve quality parity (the `ref_text` parameter meaningfully boosts speaker similarity). This phase carries the highest technical risk — new library, new API surface, new failure modes — and must be validated before any subsequent phase builds on it.

**Delivers:** Working Qwen3-TTS synthesis producing 500-char segments with 10-15s reference clips and reference transcripts. Memory-stable for full-book runs. MLX Metal cache managed. Chatterbox preserved as fallback behind config flag. Sample rate compatibility verified. Checkpoint versioned.

**Addresses:** Text-inherent emotional prosody (free with Qwen3-TTS), larger chunks (CHAR_LIMIT constant change in `segmenter.py`), longer references (clip_selector rewrite with SNR filtering and transcript support).

**Avoids:** MLX cache accumulation (Pitfall 1), broken pipeline (Pitfall 3), reference audio too long (Pitfall 2), sample rate mismatch (Pitfall 9), mlx-audio split_pattern bug (Pitfall 8 — pre-split text before engine), accent regression (Pitfall 12 — pin library version).

**Research flag:** NEEDS PHASE RESEARCH — mlx-audio is young (v0.3.1, Jan 2026) with active documented bugs (Issue #464 audio dropout, Issue #439 accent loss). Concrete API patterns, memory cleanup integration, and WAV output format must be validated before building. Spike required.

### Phase B: LLM Intelligence Upgrades (Features 4, 6, 5)

**Rationale:** Features 4 (LLM upgrade) and 6 (dialogue detection) are independent of the TTS swap and improve data quality flowing into synthesis. Feature 5 (emotion system) depends on both Feature 1 (for Qwen3-TTS semantic inference) and Feature 6 (for speech-act tags to drive post-processing). All three share the Ollama model load lifecycle and add zero memory cost to the pipeline. LLM upgrade (Feature 4) first since it benefits both dialogue detection and attribution quality immediately.

**Delivers:** `qwen3:14b` Q4_K_M attribution with KV cache quantization, hybrid regex + LLM dialogue subtype tagging (spoken/thought/shouted/whispered) with caching, `emotions.json` artifact with scene moods and line overrides, new `src/emotion/` module with resolver that maps speech-act tags to post-processing parameters (not to TTS `instruct` calls).

**Addresses:** LLM model upgrade (config constant change in `llm_client.py`), hybrid regex + LLM dialogue detection (LLM refines only ambiguous cases; full chapters batched per call), three-layer emotion system redesigned to use text-semantic inference + speech-act post-processing.

**Avoids:** Emotional whiplash (Pitfall 5) via scene-level emotion first, Gaussian-smoothed intensity, narration segments kept emotionally neutral. LLM over-engineering (Pitfall 10) via hybrid approach. 14B model OOM (Pitfall 4) via memory monitoring and `num_ctx` reduction. Emotion system breaking synthesis (Pitfall — emotion instructions NOT passed to cloned voice Base model).

**Research flag:** NEEDS PHASE RESEARCH — the redesigned emotion system (text-semantic + speech-act post-processing instead of `instruct` parameter) is architecturally sound but empirically unvalidated. A spike is required to determine whether speech-act tag post-processing (volume adjustments for whispered/shouted) produces perceptibly better output before committing to the full implementation.

### Phase C: Production Quality Finishing (Features 7, 8, 9)

**Rationale:** Features 7 (randomized pauses), 8 (post-processing), and 9 (voice consistency) all operate on TTS output, not on the TTS engine itself. They are independent of each other and of the LLM phases. Feature 9 (voice consistency) must be last because its cosine similarity threshold calibration depends on the quality of all upstream features being stable — tuning it on preliminary output would require re-tuning after Phase A and B are finalized.

**Delivers:** Gaussian-randomized context-aware pauses (seeded per book for reproducibility), pedalboard post-processing chain applied incrementally with A/B validation at each step, voice consistency verification with per-character similarity reporting, 3-attempt capped regeneration accepting best result, 44.1kHz 192kbps ACX-grade MP3 export.

**Addresses:** Natural pause timing (Gaussian not uniform, contextually aware, seeded), professional mastering chain (incremental, Hippocratic principle), voice drift detection and regeneration.

**Avoids:** Artificial-sounding pauses (Pitfall 11 — Gaussian distribution not uniform, context-aware base durations). Post-processing degradation (Pitfall 7 — A/B gating at each step, start with LUFS only). Infinite regeneration loops (Pitfall 6 — 3-attempt cap, 0.60 initial threshold). Processing all segments through consistency check (performance trap — confidence-flagged-only strategy).

**Research flag:** STANDARD PATTERNS — pedalboard, pydub, and resemblyzer are well-documented and mature. Pause timing is straightforward. Voice consistency threshold tuning requires empirical data from Phase A output, but the implementation pattern is unambiguous.

### Phase Ordering Rationale

- Phase A before B and C: six features depend on Qwen3-TTS being stable and validated. Emotion data, dialogue subtypes, and consistency verification are all meaningless until the TTS engine is producing reliable output.
- Feature 4 (LLM upgrade) is technically independent and could ship first as a quick win. It is placed in Phase B to avoid splitting a simple config change into its own phase — the roadmap is cleaner at three phases, and the attribution quality improvement is amplified when combined with Feature 6.
- Feature 3 (reference clips) is classified as Phase A despite being independently implementable — it lands with Feature 1 because `ref_text` in `voice_map.json` is a prerequisite for Qwen3-TTS voice cloning quality and the two changes must be validated together.
- Features 7 and 8 are placed in Phase C (not earlier) to avoid testing complexity during the riskier Phases A and B.
- Feature 9 is last by design: it is a quality gate on the output of all other features and its threshold cannot be calibrated until upstream quality is stable.

### Research Flags

Phases needing deeper research before planning:
- **Phase A (TTS Engine Swap):** mlx-audio v0.3.1 has active bugs, young codebase (Jan 2026), no published M4 benchmarks. Spike API usage, memory cleanup pattern, WAV output format, and voice cloning quality before writing the full phase plan.
- **Phase B (Emotion System):** The confirmed voice-cloning + instruct incompatibility forces a redesigned emotion architecture. The redesigned approach (text-semantic + speech-act post-processing) is unvalidated. Spike what speech-act post-processing actually sounds like before committing to full implementation.

Phases with standard patterns (skip research-phase):
- **Phase C (Finishing):** pedalboard, pydub, resemblyzer, and Gaussian randomization are all well-documented with clear patterns. Threshold tuning for voice consistency requires empirical data but not architectural research.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | MEDIUM | MLX and pedalboard are HIGH (verified via PyPI and official docs). mlx-audio is MEDIUM (young library, v0.3.1, active bugs). Resemblyzer is MEDIUM (functionally stable, inactive maintenance). Ollama 14B memory is HIGH via community benchmarks. Version conflict risk (mlx-audio pins `transformers<5.0.0`) is MEDIUM. |
| Features | MEDIUM | Table stakes features are HIGH confidence. The emotion system is LOW confidence due to confirmed voice-cloning + `instruct` incompatibility. Feature priority and dependency graph are HIGH confidence. Anti-features (what NOT to build) are HIGH confidence. |
| Architecture | MEDIUM-HIGH | 5-to-7 phase expansion is architecturally sound and consistent across all research files. Component boundaries are clear. The Base vs CustomVoice model question for emotion is the one unresolved architectural decision and must be resolved via spike before Phase B planning. |
| Pitfalls | HIGH | MLX memory pitfalls are verified via official GitHub issues and MLX documentation. Emotion whiplash is backed by the Dopamine Audiobook paper. Voice consistency thresholds are backed by speaker verification research. Post-processing warnings align with broadcast audio engineering best practice. |

**Overall confidence:** MEDIUM

### Gaps to Address

- **Voice cloning + emotion architectural decision (BLOCKER for Phase B planning):** The Qwen3-TTS Base model (voice cloning) ignores `instruct`. The redesigned emotion system uses text-semantic inference and speech-act post-processing. This must be empirically validated in a spike. If text-semantic inference is insufficient and speech-act post-processing produces no perceptible improvement, the emotion system may need to be deferred to v2 entirely.
- **M4 Mac throughput benchmarks (needed for Phase A planning):** Published throughput is ~1000 chars/min on M2. M4 should be faster but no published benchmarks exist as of March 2026. This affects total synthesis runtime estimates for full-book runs. Measure during Phase A validation.
- **Cosine similarity threshold for voice consistency (needed for Phase C planning):** The 0.60 baseline from speaker verification research applies to human speech. TTS-generated audio may have different embedding characteristics. Empirical tuning against Phase A output is required. Cannot determine threshold before TTS engine is stable.
- **Ollama 14B stability on 16GB during full attribution runs (validate in Phase B):** Memory fits on paper (~10GB with KV cache quant) but real-world stability on a full novel-length attribution pass is unverified. Prepare 8B Q8_0 as fallback before starting Phase B.
- **mlx-audio transformers version pin conflict (watch during Phase A):** mlx-audio pins `transformers<5.0.0`. sentence-transformers 3.x currently works with transformers 4.x. Future upgrades could break pip resolution. Pin `sentence-transformers<4.0` defensively in `pyproject.toml`.

## Sources

### Primary (HIGH confidence)
- MLX 0.31.0: https://pypi.org/project/mlx/ — Python/macOS compatibility, memory management API
- mlx-audio 0.3.1: https://pypi.org/project/mlx-audio/ — TTS API, model variants, known bugs
- pedalboard 0.9.22: https://pypi.org/project/pedalboard/ — effects chain API, ARM64 wheel availability
- Qwen3-TTS official repo: https://github.com/QwenLM/Qwen3-TTS — model variants, voice cloning API
- Qwen3-TTS technical report: https://arxiv.org/html/2601.15621v1 — architecture, 32K token context
- Qwen3-TTS discussion #231: https://github.com/QwenLM/Qwen3-TTS/discussions/231 — Base model ignores instruct param (CRITICAL FINDING)
- Qwen3-TTS discussion #238: https://github.com/QwenLM/Qwen3-TTS/discussions/238 — inline emotion tags are feature request, not capability
- MLX memory management: https://ml-explore.github.io/mlx/build/html/usage/unified_memory.html — unified memory architecture
- MLX GitHub issues #742, #1262: memory accumulation patterns confirmed
- mlx-audio Issue #439: https://github.com/Blaizzy/mlx-audio/issues/439 — accent regression confirmed
- Pedalboard: https://github.com/spotify/pedalboard — Spotify-maintained, 300x faster than pySoX
- SpeechBrain ECAPA-TDNN: https://huggingface.co/speechbrain/spkrec-ecapa-voxceleb — speaker verification embeddings
- Resemblyzer: https://github.com/resemble-ai/Resemblyzer — 256-dim GE2E embeddings
- ACX Audio Specs 2025-2026: https://narrationbox.com/blog/acx-audio-specs-explained-2025-2026 — peak -3dB, RMS -18 to -23dB, noise -60dB
- Existing codebase (direct analysis): all modules in `src/` — pipeline structure, interface contracts, data flow

### Secondary (MEDIUM confidence)
- mlx-audio Qwen3-TTS README: https://github.com/Blaizzy/mlx-audio/blob/main/mlx_audio/tts/models/qwen3_tts/README.md — API patterns, 6-bit memory benchmarks (3.88GB)
- Qwen3-TTS voice cloning guide: https://ocdevel.com/blog/20260302-qwen-tts-voice-cloning — 10-15s sweet spot, transcript boosts similarity 0.75->0.89
- Qwen3-TTS with MLX-Audio on macOS: https://mybyways.com/blog/qwen3-tts-with-mlx-audio-on-macos — ~1000 chars/min on M2, split_pattern bug
- Dopamine Audiobook paper: https://arxiv.org/html/2504.11002v1 — "averaged emotion" TTS problem, emotional whiplash
- Cosine similarity for speaker verification: https://www.researchgate.net/figure/... — 0.60 baseline for same-speaker threshold
- Ollama Qwen3 14B memory: https://github.com/ollama/ollama/issues/10994 — community benchmarks
- Resemblyzer minimum audio duration: https://periodicals.karazin.ua/mia/article/view/28479 — 2.63s for reliable embedding
- Audacity audiobook mastering chain: https://support.audacityteam.org/audio-editing/audiobook-mastering — EQ -> compression -> limiting order

### Tertiary (LOW confidence)
- Qwen3-TTS performance ~1000 chars/min on M2: https://mybyways.com/blog/qwen3-tts-with-mlx-audio-on-macos — single blog post, M2 not M4
- 1.7B RAM requirements: https://github.com/kapi2800/qwen3-tts-apple-silicon — refers to non-quantized; 8-bit should be ~3GB
- LibriTTS-R quality vs LibriTTS-P: https://www.openslr.org/141/ — dataset page, quality benefits not formally benchmarked for this specific use case

---
*Research completed: 2026-03-04*
*Ready for roadmap: yes*
