# Architecture Patterns

**Domain:** EPUB-to-audiobook pipeline v1.1 improvements
**Researched:** 2026-03-04
**Overall confidence:** MEDIUM-HIGH (existing architecture well-understood; Qwen3-TTS MLX integration details need validation)

## Existing Architecture (v1.0 Baseline)

The current pipeline is five strictly sequential phases, each reading from disk and writing to disk:

```
Phase 1: Parse       EPUB -> segments.json
Phase 2: Attribute   segments.json -> characters.json + attributed.json  (Ollama loaded)
Phase 3: Match       characters.json + attributed.json -> voice_map.json  (Ollama loaded)
Phase 4: Synthesize  attributed.json + voice_map.json -> wavs/           (Ollama unloaded, Chatterbox loaded)
Phase 5: Assemble    wavs/ -> chapters/*.mp3 + audiobook.mp3             (Chatterbox loaded briefly for announcements)
```

**Memory boundary:** Between Phase 3 and Phase 4, `unload_model()` evicts Ollama's Qwen3 8B (~5GB) before Chatterbox TTS (~3GB + PyTorch overhead = ~5-6GB total) loads. This is the critical constraint on a 16GB M4 Mac.

**Data flow:** All inter-phase data is JSON on disk. Audio intermediates are per-segment WAV files organized as `wavs/ch{NN}/seg_{NNNN}.wav`. This enables checkpoint/resume for long synthesis runs.

**Key existing interfaces:**
- `TTSEngine.generate(text, ref_clip_path, segment_type, exaggeration, cfg_weight) -> torch.Tensor`
- `call_llm_structured(system_prompt, user_content, schema_class) -> Pydantic model`
- `select_reference_clip(speaker_id, libritts_root) -> str | None`
- `_get_silence_ms(prev_segment, curr_segment, config) -> int`

## Recommended Architecture (v1.1)

### Phase Evolution: From 5 Phases to 7 Phases

The 9 improvements map onto a 7-phase pipeline. Two new phases are inserted; the rest are modifications to existing phases.

```
Phase 1: Parse       EPUB -> segments.json                                (MODIFIED -- LLM dialogue detection)
Phase 2: Attribute   segments.json -> characters.json + attributed.json   (MODIFIED -- LLM upgrade, emotion baselines)
Phase 3: Emotion     attributed.json + segments.json -> emotions.json     (NEW)
Phase 4: Match       characters.json + attributed.json -> voice_map.json  (MODIFIED -- longer refs with transcripts)
                     --- Ollama unload boundary ---
Phase 5: Synthesize  attributed.json + voice_map.json + emotions.json -> wavs/ (REWRITTEN -- Qwen3-TTS via MLX)
Phase 6: Verify      wavs/ + voice_map.json -> verify_report.json         (NEW)
Phase 7: Assemble    wavs/ -> chapters/*.mp3 + audiobook.mp3              (MODIFIED -- post-processing, randomized pauses)
```

### Memory Lifecycle (16GB Budget)

```
Phase 1 (Parse):      Ollama qwen3:14b Q4_K_M           ~9 GB   <-- now uses LLM for dialogue detection
Phase 2 (Attribute):  Ollama qwen3:14b Q4_K_M (reuse)   ~9 GB   <-- same model, no reload
Phase 3 (Emotion):    Ollama qwen3:14b Q4_K_M (reuse)   ~9 GB   <-- same model, no reload
Phase 4 (Match):      Ollama qwen3:14b Q4_K_M (reuse)   ~9 GB   <-- same model, no reload
                      --- Ollama unload boundary ---
Phase 5 (Synthesize): mlx-audio Qwen3-TTS 1.7B 6-bit   ~4 GB
Phase 6 (Verify):     ECAPA-TDNN via speechbrain        ~1 GB
                      + mlx-audio Qwen3-TTS (if regen)  ~4 GB   <-- conditional reload
Phase 7 (Assemble):   Qwen3-TTS for announcements       ~4 GB   <-- or reuse from Phase 5/6
                      + pydub/pedalboard (CPU)           ~0.5 GB
```

**Critical insight:** Qwen3-TTS 1.7B at 6-bit quantization uses only ~4GB via MLX (verified from mlx-audio benchmarks: 3.88GB at batch-1). This is dramatically less than Chatterbox's ~3GB + PyTorch overhead (~5-6GB total). The MLX model can coexist with the ECAPA-TDNN speaker embedding model (~1GB) within the 16GB budget. This means Phases 5, 6, and 7 do NOT need the strict load/unload dance that v1.0 required between Ollama and Chatterbox.

**LLM phases (1, 2, 3, 4)** all use the same Ollama model and can share a single loaded instance. The Emotion phase (3) is deliberately placed between Attribution (2) and Matching (4) so the LLM stays loaded across all four phases. This eliminates model reloads compared to inserting Emotion elsewhere.

### Component Boundaries

| Component | Module Location | Responsibility | Communicates With |
|-----------|----------------|---------------|-------------------|
| EPUB Parser | `src/parser/` (modify) | Parse EPUB, LLM-based dialogue detection | Ollama (for dialogue detection) |
| Character Extractor | `src/attribution/extractor.py` (extend) | Extract character profiles + emotion baselines | Ollama |
| Speaker Attributor | `src/attribution/attributor.py` (unchanged) | Attribute speakers to dialogue | Ollama |
| Emotion Analyzer | `src/emotion/` (NEW module) | Scene mood + line-level emotion | Ollama |
| Voice Matcher | `src/matching/` (unchanged logic) | Match characters to LibriTTS speakers | Ollama |
| Clip Selector | `src/matching/clip_selector.py` (rewrite) | Select longer, SNR-filtered refs + transcripts | LibriTTS-R audio + text files |
| TTS Engine | `src/synthesis/tts_engine.py` (REWRITE) | Qwen3-TTS via mlx-audio | mlx-audio, reference WAVs |
| Synthesizer | `src/synthesis/synthesizer.py` (modify) | Synthesis loop with emotion params | TTS Engine, emotions.json |
| Voice Verifier | `src/verify/` (NEW module) | Embedding-based drift detection | speechbrain ECAPA-TDNN, WAV files |
| Post-Processor | `src/assembly/postprocessor.py` (NEW file) | Trim, de-click, EQ, compress | pedalboard, WAV files |
| Concatenator | `src/assembly/concatenator.py` (modify) | Randomized pauses, crossfades | WAV files, pydub |
| Encoder | `src/assembly/encoder.py` (modify) | 44.1kHz 192kbps export | ffmpeg |
| Pipeline | `src/pipeline.py` (modify) | Orchestrate 7 phases | All modules |

### Data Flow

```
EPUB file
    |
    v  Phase 1 (Parse -- now with LLM dialogue subtyping)
segments.json
  [id, chapter, type*, text, char_count]
  * type now includes: spoken, thought, shouted, whispered
    |
    v  Phase 2 (Attribute -- with extended voice baselines)
characters.json + attributed.json
  characters.json adds: default_emotion, emotion_range per character
  attributed.json: [id, chapter, type, text, speaker, confidence]
    |
    v  Phase 3 (Emotion -- NEW)
emotions.json
  { scenes: [{chapter, scene_index, start_seg, end_seg, mood}],
    overrides: [{segment_id, emotion, reason}] }
    |
    v  Phase 4 (Match -- with ref transcripts)
voice_map.json
  now includes: ref_text per speaker (transcript of reference audio)
    |
    v  --- Ollama unload boundary ---
    |
    v  Phase 5 (Synthesize -- Qwen3-TTS via MLX)
wavs/ch{NN}/seg_{NNNN}.wav
  uses: voice_map (ref audio + transcript), emotions.json (per-segment instruction)
    |
    v  Phase 6 (Verify -- NEW)
verify_report.json
  + regenerated WAVs for drifted segments
    |
    v  Phase 7 (Assemble -- with post-processing)
chapters/*.mp3 + audiobook.mp3
  44.1kHz mono 192kbps CBR
```

## Where Each Improvement Lives

### 1. Qwen3-TTS 1.7B via MLX (Phase 5 -- REWRITE tts_engine.py)

**What changes:** Replace `src/synthesis/tts_engine.py` entirely. Remove Chatterbox, PyTorch, torchaudio, MPS logic. Replace with mlx-audio.

**Current interface (Chatterbox):**
```python
class TTSEngine:
    def load_model(self)
    def generate(self, text, ref_clip_path, segment_type, exaggeration, cfg_weight) -> torch.Tensor
    def save_wav_atomic(self, wav_tensor, output_path) -> bool
    def cleanup_memory(self)
    def unload(self)
```

**New interface (Qwen3-TTS):**
```python
class TTSEngine:
    def load_model(self)
    def generate(
        self, text: str,
        ref_audio: str,        # reference WAV path
        ref_text: str,         # transcript of reference audio (NEW -- critical for quality)
        emotion: str | None,   # emotion instruction (NEW -- from emotions.json)
        segment_type: str,
    ) -> np.ndarray            # mx.array converted to numpy for WAV saving
    def save_wav_atomic(self, audio_array, output_path, sample_rate) -> bool
    def cleanup_memory(self)
    def unload(self)
```

**Key differences from Chatterbox:**
- No PyTorch dependency for TTS. MLX manages its own memory via Apple's unified memory.
- No MPS fallback hackery (`PYTORCH_ENABLE_MPS_FALLBACK`, component-wise `.to("mps")`). MLX runs natively on Apple Silicon GPU.
- Voice cloning requires both reference audio AND its transcript. Providing the transcript boosts speaker similarity from ~0.75 to ~0.89 (significant quality uplift).
- Emotion control via `instruct` parameter (natural language string like "Angry and forceful" or "Whispering softly").
- `exaggeration` and `cfg_weight` parameters are removed (Chatterbox-specific concepts).
- Output is `mx.array`, not `torch.Tensor`. Save via `soundfile` or `scipy.io.wavfile`, not `torchaudio`.
- The `ensure_ollama_unloaded()` call stays -- Ollama must still be evicted before TTS loads.

**Dependency changes:**
- REMOVE from TTS path: `chatterbox-tts`, `torch`, `torchaudio`
- ADD: `mlx-audio` (includes `mlx` as dependency, Apple-only)
- ADD: `soundfile` for WAV I/O without torch
- KEEP: `torch` is still needed for Phase 6 (Verify) via speechbrain, and for Phase 7 announcements if we keep that pattern (or switch announcements to Qwen3-TTS too)

**Reference audio transcript:** The `voice_map.json` schema must be extended to store the transcript of each reference clip. The clip_selector already selects WAV files from LibriTTS-R; it needs to also locate the corresponding `.normalized.txt` file that LibriTTS-R provides alongside each WAV.

**Announcer impact:** `src/assembly/announcer.py` currently imports `TTSEngine` and `SynthesisConfig` from the synthesis module for chapter announcements. This needs updating to use the new Qwen3-TTS engine. Since the announcer is called during Phase 7 (Assemble), and Qwen3-TTS at ~4GB can stay loaded, this is architecturally clean.

**Confidence:** MEDIUM. The mlx-audio Python API for Qwen3-TTS voice cloning is documented but the library is young (v0.3.1 as of Jan 2026). The API is: `model.generate(text, ref_audio=path, ref_text=transcript)`. The 6-bit quantized 1.7B model at ~4GB memory is well-evidenced from mlx-audio benchmarks. Known risks: generation hangs with reference audio >15s, Chinese accent bleed in English voices with some models, throughput of ~1,000 chars/min on M2 (M4 should be faster).

### 2. Larger Chunk Sizes (Phase 1 + Phase 5 -- MODIFY)

**What changes in parser (`src/parser/segmenter.py`):**
- Change `CHAR_LIMIT = 280` to `CHAR_LIMIT = 500` (or make configurable via `SynthesisConfig`).
- The splitting logic in `split_to_segments()` and `_split_long_sentence()` already handles arbitrary limits. Only the constant changes.

**What changes in synthesis (`src/synthesis/synthesizer.py`):**
- Remove or raise `_split_long_text(text, max_chars=280)`. Qwen3-TTS handles longer inputs natively.
- Or adjust `max_chars` to match the new parser limit.

**Why 500 and not 600:** Qwen3-TTS's `max_new_tokens=2048` for audio output constrains how much text can be processed per call. At roughly 1,000 chars/minute throughput, 500 chars produces ~30s of audio, which is a reasonable upper bound before prosody degrades. Start at 500, tune empirically.

**Breaking change:** Changing `CHAR_LIMIT` invalidates all cached `segments.json` files from v1.0 runs. Existing checkpoint/resume data is also invalid since segment IDs will shift. Must document this as a breaking change for re-runs.

**Confidence:** HIGH. The existing code is parameterized to support this. The only question is the optimal value, which requires empirical testing.

### 3. Longer Voice References (Phase 4 -- REWRITE clip_selector.py)

**What changes:** Current logic selects the single longest WAV per speaker. New logic should:
1. Concatenate multiple WAVs from the same speaker up to 10-15 seconds total.
2. Filter by SNR (signal-to-noise ratio) -- prefer clean recordings.
3. Store the transcript alongside the clip path in `voice_map.json`.

**New clip_selector.py interface:**
```python
@dataclass
class ReferenceClip:
    wav_path: str           # path to concatenated or selected WAV
    transcript: str         # text spoken in the reference audio
    duration_s: float       # actual duration
    snr_db: float | None    # measured SNR if computed

def select_reference_clip(
    speaker_id: str,
    libritts_root: Path,
    target_duration_s: float = 12.0,   # target 10-15s
    min_snr_db: float = 15.0,          # minimum SNR threshold
) -> ReferenceClip | None:
```

**Transcript source:** LibriTTS-R stores normalized text transcripts alongside each WAV file as `{utterance_id}.normalized.txt`. The clip selector reads and concatenates these.

**Impact on voice_map.json schema:** The `VoiceAssignment` model needs a new `ref_text: str` field for the reference transcript. Existing v1.0 `voice_map.json` files need a migration path (default `ref_text` to empty string for backward compatibility).

**Qwen3-TTS reference length sweet spot:** 10-15 seconds. Beyond 15s, quality plateaus and generation hangs become more likely (model fails to emit end-of-sequence token). The clip selector should target 12s and hard-cap at 15s.

**Confidence:** HIGH. LibriTTS-R file structure is well-understood (speaker_id/chapter_id/utterance_id.wav + .normalized.txt). Concatenation is straightforward with pydub or numpy. The transcript requirement is the most important architectural insight -- without it, voice cloning quality drops significantly.

### 4. LLM Model Upgrade (Phases 1-4 -- MODIFY llm_client.py)

**What changes:**
- `MODEL = "qwen3:8b"` becomes `MODEL = "qwen3:14b"` (or `"qwen3:8b-q8_0"` for higher quantization at same model size).
- `CONTEXT_WINDOW = 32768` may increase to `65536` with the 14B model.

**Memory analysis:**
- Qwen3 14B Q4_K_M: ~9GB in Ollama. Fits within 16GB with ~7GB for OS + app.
- Qwen3 8B Q8_0: ~9GB in Ollama (same memory, different quality tradeoff).
- The 14B Q4_K_M is likely the better choice: more parameters at lower precision beats fewer parameters at higher precision for structured output tasks like attribution.

**Impact:** All LLM phases (Parse dialogue detection, Attribution, Emotion, Matching) benefit from the upgrade. No code logic changes -- just the model constant and potentially context window size.

**Confidence:** HIGH. Ollama model swaps are trivial. Memory budget verified by existing community benchmarks.

### 5. Three-Layer Emotion System (NEW Phase 3 -- NEW MODULE `src/emotion/`)

This is the most architecturally significant addition. It produces a new intermediate artifact (`emotions.json`) consumed by the synthesis phase.

**Architecture decision: NEW phase, NOT extension of attribution.**

Rationale:
- Attribution (Phase 2) is already complex with extraction + merge + attribution passes.
- Emotion analysis requires a different prompt strategy (scene-level context, not segment-level speaker identification).
- The emotion data structure is orthogonal to speaker attribution -- it decorates segments with *how* to speak, not *who* speaks.
- A separate phase keeps each phase single-responsibility and independently cacheable.
- The Ollama model stays loaded across Phases 1-4 -- no memory cost to having a separate phase.

**Three layers:**

| Layer | Scope | When Computed | Stored In |
|-------|-------|---------------|-----------|
| 1. Character voice baseline | Per character | Phase 2 extraction (extend existing) | `characters.json` (extend `VoiceQualities`) |
| 2. Scene mood | Per scene (between scene breaks) | Phase 3 emotion pass (NEW) | `emotions.json` `scenes[]` |
| 3. Line-level overrides | Per dialogue segment | Phase 3 emotion pass (NEW) | `emotions.json` `overrides[]` |

**Layer 1: Character Voice Baseline** (extend existing `CharacterProfile`)

Already partially exists in `CharacterProfile.voice_qualities` with pitch, pace, tone, accent. Extend the `VoiceQualities` model:
```python
class VoiceQualities(BaseModel):
    pitch: str
    pace: str
    tone: str
    accent: str
    # NEW fields
    default_emotion: str = "neutral"      # e.g., "calm", "cheerful", "gruff"
    emotion_range: list[str] = []         # e.g., ["stern", "warm", "angry"]
```

This is computed during character extraction (Phase 2) by the existing LLM prompts with extended instructions. Minimal code change to `extractor.py` -- just extend the prompt and the Pydantic model.

**Layer 2: Scene Mood Analysis** (new, in Phase 3)

Group segments by scene (delimited by `scene_break` segments). For each scene, ask the LLM to describe the overall emotional mood in 2-5 words.

Output structure:
```json
{
  "scenes": [
    {"chapter": 1, "scene_index": 0, "start_segment_id": 0, "end_segment_id": 42,
     "mood": "tense and foreboding"},
    {"chapter": 1, "scene_index": 1, "start_segment_id": 43, "end_segment_id": 89,
     "mood": "warm reunion"}
  ]
}
```

**Layer 3: Line-Level Emotion Overrides** (new, in Phase 3)

For dialogue segments where the emotion differs from the scene mood or character baseline, generate a specific emotion instruction:
```json
{
  "overrides": [
    {"segment_id": 45, "emotion": "shouting angrily", "reason": "character erupts after insult"},
    {"segment_id": 67, "emotion": "whispering fearfully", "reason": "character hiding from danger"}
  ]
}
```

The LLM is asked to identify ONLY segments where the emotion clearly deviates from the scene mood. Most segments inherit the scene mood and do not need overrides. This keeps the override list sparse and the LLM calls efficient.

**Emotion resolution at synthesis time (Phase 5):**
```python
def resolve_emotion(segment, character_profile, scene_mood, overrides_map):
    """Combine 3 emotion layers into a single TTS instruction string."""
    # Layer 3 override takes precedence
    if segment["id"] in overrides_map:
        return overrides_map[segment["id"]]["emotion"]
    # Layer 2 scene mood as base
    base = scene_mood
    # Layer 1 character baseline modifies delivery
    char_tone = character_profile.voice_qualities.default_emotion
    if char_tone != "neutral":
        return f"{base}, with a {char_tone} voice"
    return base
```

The resolved string (e.g., "Tense and foreboding, with a gruff voice" or "Shouting angrily") is passed directly to Qwen3-TTS's `instruct` parameter.

**New module structure:**
```
src/emotion/
    __init__.py
    models.py           # EmotionScene, EmotionOverride, EmotionMap
    scene_analyzer.py   # LLM-based scene mood extraction
    line_analyzer.py    # LLM-based line-level overrides
    resolver.py         # Combine 3 layers into per-segment instruction
```

**CRITICAL OPEN QUESTION:** Qwen3-TTS has three model types: Base (voice cloning from reference audio), CustomVoice (emotion control with preset voices), and VoiceDesign (voice creation from text descriptions). Voice cloning uses the Base model. Emotion control uses the CustomVoice model. Whether you can simultaneously clone a voice AND control emotion with a single model call is unclear from current documentation. If not, the architecture needs either:
- Option A: Use Base model for voice cloning and accept limited emotion control (rely on text content to drive natural prosody).
- Option B: Generate with Base for voice, then use CustomVoice to re-synthesize with emotion (2x synthesis time, quality loss from double-generation).
- Option C: Use VoiceDesign to create a voice from description that approximates the reference, then use emotion control with that designed voice (loses cloning fidelity).

This is the single biggest technical risk for v1.1 and needs a dedicated spike before committing to the emotion system architecture.

**Confidence:** MEDIUM. The three-layer architecture is sound. The emotion labels driving Qwen3-TTS need empirical validation. The Base vs CustomVoice model question is a blocker that must be resolved in phase-specific research.

### 6. LLM-Based Dialogue Detection (Phase 1 -- MODIFY segmenter.py)

**What changes:**
- Replace `classify_block()` regex-based dialogue detection with hybrid regex + LLM approach.
- Add new segment subtypes: "spoken", "thought", "shouted", "whispered".

**Architecture decision: Hybrid approach -- regex first pass, LLM refinement.**

Pure LLM dialogue detection on every paragraph would be slow (2-8s per LLM call). Instead:
1. Keep regex detection for obvious cases (quoted text with curly/straight quotes).
2. Use LLM to refine ambiguous cases and classify dialogue subtypes.
3. Batch multiple paragraphs per LLM call (send a chapter's worth at once).

**New segment types:**
```python
class SegmentType(str, Enum):
    NARRATION = "narration"
    DIALOGUE = "dialogue"                # Keep for backward compat
    DIALOGUE_SPOKEN = "spoken"           # NEW -- standard spoken dialogue
    DIALOGUE_THOUGHT = "thought"         # NEW -- internal monologue
    DIALOGUE_SHOUTED = "shouted"         # NEW -- emphatic delivery
    DIALOGUE_WHISPERED = "whispered"     # NEW -- quiet delivery
    CHAPTER_HEADING = "chapter_heading"
    SCENE_BREAK = "scene_break"
```

**Impact on Phase 1 memory:** Phase 1 now needs Ollama loaded. The pipeline orchestration changes from "Phase 1 is model-free" to "Phases 1-4 all use Ollama." The LLM is loaded for dialogue detection, then stays loaded through Attribution, Emotion, and Matching.

**Impact on downstream phases:**
- Attribution (Phase 2): No change. All dialogue subtypes are treated as dialogue for speaker identification.
- Emotion (Phase 3): Dialogue subtypes feed directly into line-level emotion. "shouted" implies forceful emotion, "whispered" implies quiet/fearful. Reduces the work Phase 3 needs to do.
- Synthesis (Phase 5): Subtypes map to default emotion instructions when no override exists: `shouted -> "shouting forcefully"`, `whispered -> "whispering softly"`, `thought -> "reflective internal monologue"`.
- Assembly (Phase 7): Silence duration logic uses segment type. No changes needed -- all dialogue subtypes use the same paragraph silence.

**Confidence:** MEDIUM. The hybrid approach is sound, but adds LLM latency to Phase 1 which was previously fast (~seconds). Needs batching (entire chapter per LLM call) for acceptable speed. The dialogue subtype vocabulary (spoken/thought/shouted/whispered) is minimal and covers the common cases.

### 7. Randomized Pause Timing (Phase 7 -- MODIFY concatenator.py + models.py)

**What changes:**
- Replace fixed silence durations in `AssemblyConfig` with randomized ranges.
- Add context-aware randomization based on speaker changes.

**Current (fixed durations in `AssemblyConfig`):**
```python
sentence_silence_ms: int = 400
paragraph_silence_ms: int = 900
scene_break_silence_ms: int = 2500
```

**New (randomized ranges):**
```python
@dataclass
class SilenceRange:
    min_ms: int
    max_ms: int
    def sample(self) -> int:
        return random.randint(self.min_ms, self.max_ms)

# In AssemblyConfig:
sentence_silence: SilenceRange = SilenceRange(300, 500)
paragraph_silence: SilenceRange = SilenceRange(700, 1100)
scene_break_silence: SilenceRange = SilenceRange(2000, 3000)
speaker_change_bonus_ms: int = 200  # extra pause on speaker transitions
```

**Speaker change detection in `_get_silence_ms()`:**
```python
if prev_segment.get("speaker") != curr_segment.get("speaker"):
    silence_ms += config.speaker_change_bonus_ms
```

**Confidence:** HIGH. This is a straightforward modification. The randomization prevents the robotic cadence of identical pauses. The speaker change bonus adds natural "beat" between dialogue turns that professional narrators use.

### 8. Post-Processing Pipeline (Phase 7 -- NEW FILE `src/assembly/postprocessor.py`)

**Architecture decision: Part of assembly (Phase 7), NOT a separate phase.**

Post-processing operates on WAV segments before concatenation and on chapter audio after concatenation. It belongs in the assembly phase as pre-concatenation and post-concatenation processing steps.

**New file: `src/assembly/postprocessor.py`**

**Per-segment processing (before concatenation):**
```python
def process_segment(wav_path: Path, config: PostProcessConfig) -> Path:
    """Apply per-segment audio cleanup. Returns path to processed WAV."""
    # 1. Trim leading/trailing silence (keep 50ms padding)
    # 2. De-click (remove TTS glitch artifacts)
    # 3. Noise gate (suppress low-level hiss between words)
    return processed_path
```

**Per-chapter processing (after concatenation, before LUFS normalization):**
```python
def process_chapter(audio_array: np.ndarray, sample_rate: int,
                    config: PostProcessConfig) -> np.ndarray:
    """Apply chapter-level processing."""
    # 1. Gentle compression (reduce dynamic range for consistent listening)
    # 2. EQ (subtle low-cut at 80Hz, presence boost at 3kHz)
    # 3. Resample to 44.1kHz if needed
    return processed_audio
```

**Technology: Spotify Pedalboard**

Use `pedalboard` (Spotify's audio effects library) for effects processing. It is up to 300x faster than pySoX, supports Compressor, NoiseGate, LowShelfFilter, HighShelfFilter out of the box, and is C++-backed with Python bindings.

```python
import pedalboard
from pedalboard import Compressor, NoiseGate, LowShelfFilter, HighShelfFilter

board = pedalboard.Pedalboard([
    NoiseGate(threshold_db=-40, ratio=4.0),
    Compressor(threshold_db=-20, ratio=2.0, attack_ms=10, release_ms=100),
    LowShelfFilter(cutoff_frequency_hz=80, gain_db=-6),   # cut rumble
    HighShelfFilter(cutoff_frequency_hz=3000, gain_db=2),  # presence boost
])
processed = board(audio_array, sample_rate)
```

**Where in the assembly pipeline (modified `assembler.py` flow):**
```
Per-segment WAVs
    -> postprocessor.process_segment()  (NEW -- trim, de-click, gate)
    -> concatenator.assemble_chapter()  (existing, with randomized pauses)
    -> postprocessor.process_chapter()  (NEW -- compress, EQ)
    -> normalizer.normalize_audio()     (existing -- LUFS normalization)
    -> encoder.export_chapter_mp3()     (existing, updated: 44.1kHz 192kbps)
```

**Export format upgrade:**
- Current: 24kHz mono 64kbps CBR MP3
- New: 44.1kHz mono 192kbps CBR MP3 (ACX/Audible standard for indie publishers)
- Requires resampling WAVs from Qwen3-TTS output sample rate to 44.1kHz

**Confidence:** HIGH. Pedalboard is mature (maintained by Spotify), pydub is already a dependency. The processing chain is standard broadcast audio engineering applied to audiobook production.

### 9. Voice Consistency Pass (NEW Phase 6 -- NEW MODULE `src/verify/`)

**Architecture decision: NEW phase between synthesis and assembly.**

The voice consistency check needs to:
1. Load each generated WAV segment.
2. Extract a speaker embedding.
3. Compare against the reference clip's embedding.
4. Flag segments where cosine similarity drops below a threshold.
5. Optionally regenerate flagged segments.

**This cannot be part of assembly** because regeneration requires reloading the TTS engine, which assembly should not do. And it cannot be part of synthesis because it needs the complete set of WAVs to analyze patterns.

**New module structure:**
```
src/verify/
    __init__.py
    models.py         # VerifyConfig, SegmentVerification, VerifyReport
    embedder.py       # Extract speaker embeddings via ECAPA-TDNN
    comparator.py     # Compare embeddings, flag drift
    regenerator.py    # Reload TTS and regenerate flagged segments
```

**Speaker embedding technology:** SpeechBrain ECAPA-TDNN (`speechbrain/spkrec-ecapa-voxceleb`). This produces 192-dimensional speaker embeddings. Cosine similarity threshold of ~0.7 is a reasonable starting point for "same speaker" verification (needs empirical tuning for TTS-generated audio). The model is small (~80MB weights) and runs on CPU efficiently.

**Memory coexistence:** ECAPA-TDNN (~1GB with PyTorch) + Qwen3-TTS (~4GB MLX) = ~5GB. Within 16GB budget with margin. SpeechBrain uses PyTorch, which means `torch` gets loaded for verification. But MLX and PyTorch use separate memory pools (PyTorch on CPU, MLX on Apple Silicon unified memory), so they coexist.

**Regeneration flow:**
```python
def verify_and_regenerate(book_dir, voice_map, emotions_map, config):
    # 1. Extract reference embeddings for each speaker
    # 2. For each WAV in wavs/:
    #    a. Extract segment embedding
    #    b. Compare to reference embedding
    #    c. If cosine_sim < threshold, add to regen_queue
    # 3. If regen_queue not empty:
    #    a. Load TTS engine (Qwen3-TTS)
    #    b. Regenerate flagged segments (with same emotion params)
    #    c. Re-verify regenerated segments
    #    d. Unload TTS
    # 4. Write verify_report.json
```

**Output artifact (`verify_report.json`):**
```json
{
  "total_segments": 450,
  "verified_ok": 438,
  "flagged": 12,
  "regenerated": 10,
  "still_flagged": 2,
  "per_speaker_similarity": {
    "narrator": {"mean": 0.85, "min": 0.72, "max": 0.91},
    "Kvothe": {"mean": 0.82, "min": 0.68, "max": 0.89}
  }
}
```

**Confidence:** MEDIUM. SpeechBrain ECAPA-TDNN is well-established for speaker verification with natural speech. The open question is whether cosine similarity between TTS-generated audio and real human reference audio produces meaningful "same speaker" signals. TTS voices may have different embedding characteristics than natural speech. The threshold will need empirical tuning, and false positives/negatives are likely during initial calibration.

## Patterns to Follow

### Pattern 1: Phase Interface Contract (Existing -- Maintain)

**What:** Every phase reads JSON from disk and writes JSON/WAV to disk. No in-memory data passing between phases.

**When:** Always. This is the fundamental architectural constraint.

**Why:** Enables checkpoint/resume, independent re-runs of individual phases, and strict memory isolation between LLM and TTS runtimes.

```python
# Phase 3 (Emotion) reads attributed.json + segments.json, writes emotions.json
def run_emotion_analysis(book_dir: Path) -> Path:
    attributed = json.load(open(book_dir / "attributed.json"))
    segments = json.load(open(book_dir / "segments.json"))
    characters = json.load(open(book_dir / "characters.json"))
    emotions = _analyze_emotions(segments, attributed, characters)
    with open(book_dir / "emotions.json", "w") as f:
        json.dump(emotions, f, indent=2)
    return book_dir / "emotions.json"
```

### Pattern 2: Late Import for Heavy Dependencies (Existing -- Extend)

**What:** Import torch, mlx, speechbrain only inside functions that use them, never at module level.

**When:** For any dependency that loads ML models or large frameworks.

**Why:** Keeps `python main.py --help` fast. Prevents importing TTS libraries during LLM phases and vice versa.

```python
# New pattern for mlx-audio in tts_engine.py
def load_model(self) -> None:
    # Late imports
    from mlx_audio.tts.utils import load_model as mlx_load
    self.model = mlx_load("mlx-community/Qwen3-TTS-12Hz-1.7B-Base-6bit")
```

### Pattern 3: Ollama Model Lifecycle (Modify -- Single Load Across Phases 1-4)

**What:** Load once at Phase 1 start, use across phases 1-4, unload once before Phase 5 TTS.

**Current behavior:** `unload_model()` is called at the end of Phase 2 (attribution) and Phase 3 (matching) independently. With the new 4-LLM-phase architecture, this wastes reload time.

**New behavior:** Remove per-phase unload calls. Only unload at the Phase 4 -> Phase 5 boundary.

```python
# pipeline.py run_full_pipeline()
run_parse(epub_path, output_dir)              # Phase 1 -- LLM loaded here
run_attribute(output_book_dir)                # Phase 2 -- LLM stays loaded
run_emotion(output_book_dir)                  # Phase 3 -- LLM stays loaded
run_match(output_book_dir, ...)               # Phase 4 -- LLM stays loaded
unload_model()                                # --- boundary ---
run_synthesize(output_book_dir)               # Phase 5 -- Qwen3-TTS loaded
run_verify(output_book_dir)                   # Phase 6 -- ECAPA-TDNN loaded
run_assemble(output_book_dir, ...)            # Phase 7 -- pydub + pedalboard
```

### Pattern 4: Emotion Passthrough Transparency

**What:** If `emotions.json` does not exist (e.g., user runs Phase 5 without Phase 3), the synthesis phase works without emotion data -- all segments synthesized with neutral/default emotion.

**When:** For any optional enhancement that decorates existing data.

**Why:** Backward compatibility. Users can skip the emotion phase and still get working audiobooks. The emotion system is additive, not required.

```python
# In synthesizer.py
emotions_path = book_dir / "emotions.json"
emotion_map = json.load(open(emotions_path)) if emotions_path.exists() else None
# ...
emotion_instruction = resolve_emotion(seg, char_profile, scene_mood, overrides) if emotion_map else None
wav = engine.generate(text, ref_audio, ref_text, emotion=emotion_instruction, ...)
```

## Anti-Patterns to Avoid

### Anti-Pattern 1: Loading Both Ollama and Qwen3-TTS Simultaneously

**What:** Never have Ollama and Qwen3-TTS models loaded at the same time.

**Why bad:** Ollama Qwen3 14B (~9GB) + Qwen3-TTS 1.7B (~4GB) = ~13GB, leaving only ~3GB for OS and app. Causes disk swapping and instability.

**Instead:** Maintain the strict boundary. All LLM work (Phases 1-4) finishes and Ollama is unloaded before any TTS work (Phases 5-7) begins.

### Anti-Pattern 2: Emotion as a Synthesis-Time LLM Computation

**What:** Doing emotion analysis inside the synthesis loop (per-segment LLM call during TTS generation).

**Why bad:** Violates the sequential memory constraint. Would require Ollama loaded during synthesis, which conflicts with Qwen3-TTS.

**Instead:** Pre-compute all emotions in Phase 3 and store in `emotions.json`. The synthesis phase reads pre-computed values only.

### Anti-Pattern 3: Monolithic Post-Processing

**What:** Applying all post-processing effects in a single pass that processes the entire audiobook at once.

**Why bad:** Memory-bounded. A 10-hour audiobook at 44.1kHz mono is ~3.5GB of uncompressed audio.

**Instead:** Process per-segment (before concatenation) and per-chapter (after concatenation). Never load the entire audiobook into memory.

### Anti-Pattern 4: Combining Verify and Assemble into One Phase

**What:** Doing voice consistency checking inside the assembly phase.

**Why bad:** If a segment fails verification and needs regeneration, the assembly phase would need to reload the TTS engine. Assembly should be a pure audio processing phase (pydub + pedalboard + ffmpeg), not an ML inference phase.

**Instead:** Keep verification as a separate Phase 6 that handles any TTS regeneration before assembly begins.

## Scalability Considerations

| Concern | Current (v1.0) | v1.1 Design | Notes |
|---------|----------------|-------------|-------|
| TTS memory | Chatterbox ~5-6GB (PyTorch+MPS) | Qwen3-TTS ~4GB (MLX 6-bit) | 1.5-2GB savings per run |
| Synthesis speed | ~1.5x realtime (Chatterbox MPS) | ~1,000 chars/min on M2 (MLX) | Needs M4 benchmarking |
| Segments per book | ~4000 (280-char limit) | ~2200 (500-char limit) | Fewer segments = fewer TTS calls |
| LLM phases | 2 phases (attr, match) | 4 phases (parse, attr, emotion, match) | Single model load, no memory cost |
| Post-processing | Light (LUFS only) | Full chain (gate, compress, EQ, LUFS) | Pedalboard is CPU-only, very fast |
| Quality gating | None | Voice consistency verification | Catches drifted segments before final output |
| Export quality | 24kHz 64kbps | 44.1kHz 192kbps | 3x file size, ACX-grade quality |

## Suggested Build Order

The 9 improvements have dependencies that constrain build order:

```
Independent (can build in any order, no dependencies):
  [2] Larger chunks          -- change one constant in segmenter.py
  [4] LLM model upgrade      -- change one constant in llm_client.py
  [7] Randomized pauses       -- assembly modification only

Prerequisites for TTS swap:
  [3] Longer voice refs       -- MUST build before [1] (adds ref_text to voice_map)

TTS swap (biggest change):
  [1] Qwen3-TTS swap          -- depends on [3] for ref transcripts

Depends on better LLM and ideally [6]:
  [6] LLM dialogue detection  -- parser modification, benefits from [4]
  [5] Emotion system           -- new module, needs [1] for TTS emotion params, benefits from [6] subtypes

Depends on [1]:
  [8] Post-processing          -- assembly addition, needs Qwen3-TTS WAV format understanding
  [9] Voice consistency        -- new module, needs [1] output to verify against
```

**Recommended build sequence:**
1. **[4] LLM upgrade + [2] larger chunks** -- quick config wins, improve quality immediately, validate with existing pipeline
2. **[3] Longer voice refs** -- prerequisite for TTS swap (adds ref_text to voice_map schema)
3. **[1] Qwen3-TTS swap** -- biggest change, unlocks emotion support; validate quality vs Chatterbox
4. **[6] LLM dialogue detection** -- improves upstream data quality for emotion system
5. **[5] Three-layer emotion** -- the quality differentiator, needs [1] + [4] + ideally [6]
6. **[7] Randomized pauses** -- quick assembly win
7. **[8] Post-processing** -- assembly enhancement with pedalboard
8. **[9] Voice consistency** -- final quality gate, least critical path

**Phase ordering rationale:**
- [4] and [2] first because they are trivial, immediate quality wins with zero architectural risk.
- [3] before [1] because the TTS swap needs reference transcripts to achieve quality parity.
- [1] is the critical path -- everything after depends on it working well.
- [5] last among the "big" features because it depends on the most prerequisites and has the highest uncertainty (Base vs CustomVoice model question).
- [9] last overall because it is a nice-to-have quality gate, not a core quality improvement.

## Sources

- [mlx-audio GitHub repository](https://github.com/Blaizzy/mlx-audio) -- Python API, model support, benchmarks (HIGH confidence)
- [mlx-audio Qwen3-TTS README with benchmarks](https://github.com/Blaizzy/mlx-audio/blob/main/mlx_audio/tts/models/qwen3_tts/README.md) -- 6-bit memory: 3.88-4.10GB (HIGH confidence)
- [Qwen3-TTS official GitHub](https://github.com/QwenLM/Qwen3-TTS) -- model variants, voice cloning API, architecture (HIGH confidence)
- [Qwen3-TTS Voice Cloning Guide](https://ocdevel.com/blog/20260302-qwen-tts-voice-cloning) -- 10-15s ref sweet spot, transcript boosts similarity 0.75->0.89, generation hang risk >15s (MEDIUM confidence)
- [Qwen3-TTS with MLX-Audio on macOS](https://mybyways.com/blog/qwen3-tts-with-mlx-audio-on-macos) -- ~1,000 chars/min throughput on M2, practical usage patterns (MEDIUM confidence)
- [Qwen3-TTS Complete 2026 Guide](https://dev.to/czmilo/qwen3-tts-the-complete-2026-guide-to-open-source-voice-cloning-and-ai-speech-generation-1in6) -- model sizes, memory requirements, model type differences (MEDIUM confidence)
- [Pedalboard by Spotify](https://github.com/spotify/pedalboard) -- audio effects library, Compressor/NoiseGate/EQ, 300x faster than pySoX (HIGH confidence)
- [SpeechBrain ECAPA-TDNN](https://huggingface.co/speechbrain/spkrec-ecapa-voxceleb) -- speaker verification with 192-dim embeddings (HIGH confidence)
- Existing codebase: `src/pipeline.py`, `src/synthesis/tts_engine.py`, `src/synthesis/synthesizer.py`, `src/attribution/llm_client.py`, `src/attribution/attributor.py`, `src/attribution/extractor.py`, `src/parser/segmenter.py`, `src/assembly/assembler.py`, `src/assembly/concatenator.py`, `src/assembly/normalizer.py`, `src/matching/clip_selector.py`, `src/matching/models.py`, `src/attribution/models.py`, `src/parser/models.py`, `src/synthesis/models.py`, `src/assembly/models.py` (HIGH confidence -- direct code analysis)

---
*Architecture research for: v1.1 pipeline quality improvements*
*Researched: 2026-03-04*
