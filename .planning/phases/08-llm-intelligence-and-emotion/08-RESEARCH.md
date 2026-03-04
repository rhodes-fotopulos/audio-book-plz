# Phase 8: LLM Intelligence and Emotion - Research

**Researched:** 2026-03-04
**Domain:** Ollama model management, hybrid dialogue detection, speech-act tagging, three-layer emotion system, audio post-processing
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Four speech-act types only: spoken, thought, shouted, whispered — no additional subtypes
- Internal monologue (thoughts) rendered in character's own voice with softer tone, not switched to narrator
- Indirect dialogue stays as narration — only directly quoted speech gets character voices
- When regex and LLM disagree on a tag, LLM wins — it understands context better than pattern matching
- Layer 1 (voice baselines): Rich personality descriptions per character — 3-5 descriptors covering pace, tone, energy, typical emotion
- Layer 2 (scene mood): Every scene gets a mood+intensity annotation, including neutral scenes — neutral is useful information
- Layer 3 (line-level overrides): High threshold only — triggered by extreme emotional shifts (e.g., joke at a funeral, scream in calm scene). Most lines follow scene mood without override
- Emotion taxonomy: Fixed predefined set of emotion categories (6-10) that map cleanly to post-processing parameters. No free-form descriptions
- Whispered lines: Subtle volume reduction (-3 to -6 dB) — noticeably quieter but still clearly audible
- Shouted lines: Volume boost (+3 to +6 dB) with slight speed increase — feels urgent without being harsh
- Thought lines: Slightly slower pace + quieter volume — reflective, introspective feel
- Spoken lines: No adjustments (baseline)
- Adjustments are absolute per speech-act type, NOT cumulative with scene mood — simpler and more predictable
- Pre-check available RAM before loading — if below threshold, go straight to 8B without attempting 14B load
- Warn user when fallback to 8B occurs: clear message about reduced attribution quality
- Model stays resident by default (load once, reuse across LLM phases), with --low-memory config toggle to unload between phases
- Config option (--model flag or config setting) to override model selection — power users can force 8B or specify custom Ollama model name

### Claude's Discretion
- Exact fixed emotion set (which 6-10 emotions to include)
- RAM threshold for 14B vs 8B decision
- Regex patterns for initial dialogue detection pass
- How voice baseline descriptions are structured in output JSON
- Scene boundary detection heuristics

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| LLM-01 | Attribution uses qwen3:14b Q4_K_M with KV cache quantization, falling back to 8B Q8_0 if 14B exceeds 16GB memory budget | Ollama model management API, psutil RAM check, KV cache quantization |
| LLM-02 | Dialogue detection uses hybrid regex + LLM to tag lines as spoken/thought/shouted/whispered | Regex patterns for speech acts, LLM structured output with speech_act field |
| LLM-03 | Ollama model loads once at pipeline start and stays resident across all LLM phases, with explicit unload before TTS | Ollama keep_alive=-1 API, model lifecycle management |
| EMO-01 | Character extraction generates a voice_baseline field describing each character's default speaking style | CharacterProfile model extension, LLM prompt for baseline extraction |
| EMO-02 | Scene mood analysis produces one mood + intensity per scene via LLM pass | Scene boundary detection, LLM structured output for mood annotation |
| EMO-03 | Line-level emotion overrides flag only lines where speaker emotion sharply breaks from scene mood | Override detection heuristics, LLM contextual analysis |
| EMO-04 | Emotion data flows to synthesis as post-processing parameters (volume/speed adjustments for speech-act tags), not as TTS instruct prompts | pydub volume/speed API, numpy audio manipulation |
</phase_requirements>

## Summary

Phase 8 upgrades the attribution pipeline from Qwen3 8B to 14B with automatic fallback, adds hybrid dialogue detection with speech-act subtype tagging, and builds a three-layer emotion system that feeds post-processing parameters to synthesis. The existing codebase (`src/attribution/`) provides a clean foundation: `llm_client.py` has a single `MODEL` constant and `call_llm_structured()` function, `models.py` defines Pydantic schemas for LLM output, and `attributor.py` handles the chapter-by-chapter processing loop.

The key technical challenges are: (1) memory-aware model selection on 16GB Apple Silicon where 14B Q4_K_M is tight, (2) extending the segmenter's regex-only dialogue detection with LLM-based speech-act classification, (3) adding scene boundary detection and mood annotation as a new LLM pass, and (4) applying volume/speed adjustments to generated WAV files in the synthesis pipeline without degrading audio quality.

**Primary recommendation:** Extend the existing `llm_client.py` with model selection logic and keep_alive management, add a new `speech_acts.py` module for hybrid detection, create an `emotion/` subpackage for the three-layer system, and add a `post_processor.py` in synthesis for volume/speed adjustments using numpy/scipy (already available) and pydub (already a dependency).

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| ollama (Python) | >=0.6 | LLM API client — chat, ps, show, keep_alive, model management | Already in use; provides all needed model lifecycle APIs |
| pydantic | >=2.0 | Structured LLM output schemas | Already in use; Ollama's format parameter accepts model_json_schema() |
| psutil | >=5.9 | RAM availability check for model selection | Standard cross-platform system monitoring; works on Apple Silicon macOS |
| pydub | >=0.25.1 | Volume adjustment (dB gain) for post-processing | Already a dependency; clean dB-based volume API |
| numpy | (via mlx/sentence-transformers) | Speed adjustment via sample manipulation | Already available transitively; no new dependency needed |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| scipy.signal | (via sentence-transformers) | Audio resampling for speed changes without pitch shift | Only if speed adjustment needed beyond simple sample rate change |
| re (stdlib) | - | Regex patterns for initial dialogue/speech-act detection pass | First pass before LLM refinement |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| psutil for RAM check | subprocess + `sysctl hw.memsize` | macOS-only, less clean than psutil, but zero new dependency |
| pydub for volume | numpy direct manipulation | pydub has simpler dB API; numpy requires manual dBFS calculation |
| scipy for speed | librosa time_stretch | librosa is a heavy dependency; scipy already available transitively |

**New dependency:** psutil (one new pip install). Everything else already in project.

**Installation:**
```bash
pip install psutil
```

## Architecture Patterns

### Recommended Module Structure
```
src/
├── attribution/
│   ├── llm_client.py      # MODIFY: model selection, keep_alive, memory check
│   ├── models.py           # MODIFY: add speech_act, voice_baseline fields
│   ├── extractor.py        # MODIFY: extract voice_baseline per character
│   ├── attributor.py       # MODIFY: integrate speech-act tags into attribution
│   ├── speech_acts.py      # NEW: hybrid regex+LLM speech-act detection
│   └── emotion/
│       ├── __init__.py     # NEW: emotion subpackage
│       ├── models.py       # NEW: EmotionTaxonomy, SceneMood, LineOverride schemas
│       ├── scene_mood.py   # NEW: scene boundary detection + mood annotation
│       └── overrides.py    # NEW: line-level emotion override detection
├── synthesis/
│   ├── post_processor.py   # NEW: volume/speed adjustments per speech-act
│   └── synthesizer.py      # MODIFY: call post_processor after generation
└── pipeline.py             # MODIFY: model lifecycle (load once, unload before TTS)
```

### Pattern 1: Model Selection with Memory Pre-Check
**What:** Check available RAM before attempting to load a model, with graceful fallback
**When to use:** At pipeline start, before any LLM calls

```python
import psutil

MODEL_14B = "qwen3:14b"
MODEL_8B = "qwen3:8b"
RAM_THRESHOLD_GB = 12.0  # 14B Q4_K_M needs ~10-12GB; leave headroom for OS + KV cache

def select_model(override: str | None = None) -> str:
    """Select LLM model based on available memory or user override."""
    if override:
        return override

    available_gb = psutil.virtual_memory().available / (1024**3)
    if available_gb >= RAM_THRESHOLD_GB:
        return MODEL_14B
    else:
        logger.warning(
            "Available RAM %.1f GB < %.1f GB threshold — "
            "falling back to %s (reduced attribution quality)",
            available_gb, RAM_THRESHOLD_GB, MODEL_8B,
        )
        return MODEL_8B
```

### Pattern 2: Ollama Keep-Alive for Model Residency
**What:** Load model once and keep it resident across all LLM phases using keep_alive=-1
**When to use:** First LLM call in pipeline, unload explicitly before TTS

```python
from ollama import chat as ollama_chat

def preload_model(model: str) -> None:
    """Preload model into Ollama with infinite keep_alive."""
    ollama_chat(
        model=model,
        messages=[],
        keep_alive=-1,  # Keep loaded until explicit unload
    )

def unload_model(model: str) -> None:
    """Explicitly unload model from Ollama to free memory for TTS."""
    ollama_chat(
        model=model,
        messages=[],
        keep_alive=0,  # Unload immediately
    )
```

### Pattern 3: Hybrid Detection (Regex First, LLM Refines)
**What:** Two-pass speech-act detection — fast regex classifies obvious cases, LLM handles ambiguous ones
**When to use:** During attribution, after dialogue segments are identified

```python
# Pass 1: Regex classifies high-confidence patterns
regex_tag = classify_speech_act_regex(text)  # returns (tag, confidence)

# Pass 2: LLM refines low-confidence or ambiguous cases
if regex_tag.confidence < 0.8:
    llm_tag = classify_speech_act_llm(text, context)  # LLM always wins on conflict
    final_tag = llm_tag
else:
    final_tag = regex_tag
```

### Pattern 4: Scene Boundary Detection
**What:** Identify scene boundaries from existing segment data (scene_break type, chapter boundaries, significant time/location shifts in narration)
**When to use:** Before mood annotation pass

```python
# Scene boundaries already partially detected in parser:
# - SegmentType.SCENE_BREAK marks explicit breaks (*** or ---)
# - SegmentType.CHAPTER_HEADING marks chapter starts
# Group consecutive segments between boundaries into "scenes"
```

### Anti-Patterns to Avoid
- **Passing emotion as TTS instruct prompts:** Qwen3-TTS Base model ignores `instruct` parameter with cloned voices — confirmed upstream. All emotion must flow as post-processing.
- **Cumulative volume/speed adjustments:** User decided adjustments are absolute per speech-act type, not layered with scene mood. Keep the mapping simple and predictable.
- **Loading 14B without checking RAM first:** On 16GB machines, 14B can OOM the system if OS + other processes use too much memory. Always pre-check.
- **Creating a separate LLM call per line for speech-act tags:** Too slow for 3000+ segments. Batch speech-act classification by chapter/scene, same as existing attribution pattern.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| RAM availability check | Custom /proc/meminfo parser | `psutil.virtual_memory().available` | Cross-platform, handles macOS unified memory correctly |
| Volume adjustment in dB | Manual numpy dBFS math | `pydub.AudioSegment + gain` or numpy `* 10**(dB/20)` | pydub already handles edge cases (clipping, normalization) |
| Audio speed change | Custom resampling | `scipy.signal.resample` or numpy array slicing | scipy handles anti-aliasing; naive slicing causes artifacts |
| Structured LLM output | JSON string parsing + regex | `Ollama format=schema.model_json_schema()` | Already used in codebase; grammar-constrained decoding guarantees valid JSON |
| Model memory management | Manual VRAM tracking | Ollama `ps()` + `keep_alive` + `show()` APIs | Ollama manages GPU/unified memory allocation internally |

**Key insight:** The existing codebase already has the right patterns (Pydantic schemas for LLM output, Ollama chat API, pydub for audio). Phase 8 extends them rather than replacing them.

## Common Pitfalls

### Pitfall 1: 14B Model Thrashing on 16GB Machines
**What goes wrong:** Model loads successfully but KV cache allocation pushes total memory past 16GB, causing macOS swap thrashing and 10x slowdown
**Why it happens:** 14B Q4_K_M model weights are ~10GB, but KV cache at 32K context with FP16 adds 2-4GB more
**How to avoid:** (1) Enable KV cache quantization via `OLLAMA_KV_CACHE_TYPE=q8_0` environment variable — cuts KV cache memory in half. (2) Reduce context window to 16K for attribution (sufficient for chapter-level batches). (3) Check available RAM, not total RAM, to account for OS/browser usage.
**Warning signs:** First LLM call takes >60 seconds, system becomes unresponsive during generation

### Pitfall 2: Speech-Act Regex False Positives
**What goes wrong:** Regex classifies narration as dialogue (e.g., quoted titles, scare quotes, quoted words within narration)
**Why it happens:** The existing `_contains_dialogue_quote()` in segmenter.py treats ANY quoted text as dialogue — "The sign read 'No Entry'" would be classified as dialogue
**How to avoid:** Speech-act regex should operate ONLY on segments already classified as dialogue by the segmenter. The regex pass adds speech-act subtypes (spoken/thought/shouted/whispered), not dialogue detection.
**Warning signs:** High percentage of short segments tagged as shouted/whispered that are actually narration with quoted words

### Pitfall 3: Scene Mood LLM Call Explosion
**What goes wrong:** Calling the LLM once per scene for mood annotation on a 40-chapter book with 5 scenes per chapter = 200 LLM calls, adding 30+ minutes to pipeline
**Why it happens:** Naive implementation sends each scene independently
**How to avoid:** Batch scene mood annotations per chapter — send all scenes in a chapter as one LLM call with structured output returning an array of mood annotations. Same batching pattern as existing attribution.
**Warning signs:** Mood annotation pass taking longer than the attribution pass

### Pitfall 4: Audio Quality Degradation from Speed Changes
**What goes wrong:** Speed-adjusted audio has audible artifacts (clicks, pitch shifts, metallic quality)
**Why it happens:** Naive speed change via sample rate manipulation changes pitch proportionally
**How to avoid:** For the small speed adjustments needed (5-15% for thought/shouted), simple sample interpolation is acceptable. For larger changes, use scipy.signal.resample with proper anti-aliasing. Test with real synthesized audio before committing to an approach.
**Warning signs:** Shouted lines sound higher pitched; thought lines sound lower pitched

### Pitfall 5: Emotion Override Over-Triggering
**What goes wrong:** Too many lines get emotion overrides, making the audiobook sound like every sentence has dramatic emphasis
**Why it happens:** LLM tends to over-annotate — "she sighed" gets a sadness override even when the scene is already annotated as melancholy
**How to avoid:** User decision: high threshold only. Implement as a post-filter: if the line's emotion matches or is close to scene mood, suppress the override. Only sharp breaks (joy at funeral, scream in calm scene) survive.
**Warning signs:** >10% of lines in a scene getting overrides suggests threshold is too low

## Code Examples

### Extending CharacterProfile with voice_baseline
```python
# In src/attribution/models.py
class VoiceBaseline(BaseModel):
    """Default speaking style descriptors for a character."""
    model_config = ConfigDict(strict=True)

    pace: str
    """Speaking pace: "measured", "rapid", "languid", "clipped", etc."""

    tone: str
    """Vocal tone: "warm", "gravelly", "melodic", "flat", "breathy", etc."""

    energy: str
    """Energy level: "restrained", "animated", "intense", "subdued", etc."""

    typical_emotion: str
    """Default emotional register: "sardonic", "cheerful", "weary", etc."""

    description: str
    """One-sentence summary: "A slow, gravelly voice with weary patience"."""


class CharacterProfile(BaseModel):
    # ... existing fields ...
    voice_baseline: VoiceBaseline | None = None
    """Default speaking style (Phase 8+). None for backward compatibility."""
```

### Speech-Act Regex Patterns
```python
# In src/attribution/speech_acts.py
import re

# Shouted: text contains ALL-CAPS words (3+ chars), exclamation marks,
# or explicit tags like "shouted", "screamed", "yelled"
SHOUTED_PATTERNS = [
    re.compile(r'\b[A-Z]{3,}\b'),           # ALL-CAPS words
    re.compile(r'!{2,}'),                     # Multiple exclamation marks
    re.compile(r'\b(shout|scream|yell|bellow|roar)(?:ed|ing|s)?\b', re.I),
]

# Whispered: explicit tags like "whispered", "murmured", "hissed"
WHISPERED_PATTERNS = [
    re.compile(r'\b(whisper|murmur|hiss|breathe|mutter)(?:ed|ing|s)?\b', re.I),
]

# Thought: italic markers, "thought", "wondered", internal monologue patterns
THOUGHT_PATTERNS = [
    re.compile(r'\b(thought|wondered|mused|pondered|reflected)\b', re.I),
    re.compile(r'\b(to (?:her|him|them)self)\b', re.I),
]
```

### Emotion Taxonomy (Recommended 8 Categories)
```python
# In src/attribution/emotion/models.py
from enum import Enum

class EmotionCategory(str, Enum):
    """Fixed emotion taxonomy mapping to post-processing parameters."""
    NEUTRAL = "neutral"
    JOY = "joy"
    SADNESS = "sadness"
    ANGER = "anger"
    FEAR = "fear"
    SURPRISE = "surprise"
    DISGUST = "disgust"
    TENDERNESS = "tenderness"

class MoodIntensity(str, Enum):
    """Scene mood intensity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
```

### Post-Processing Volume Adjustment
```python
# In src/synthesis/post_processor.py
import numpy as np

# Speech-act to post-processing parameter mapping
SPEECH_ACT_PARAMS = {
    "spoken":    {"volume_db": 0.0,  "speed_factor": 1.0},
    "whispered": {"volume_db": -4.5, "speed_factor": 1.0},   # -3 to -6 dB, midpoint
    "shouted":   {"volume_db": +4.5, "speed_factor": 1.08},  # +3 to +6 dB, slight speedup
    "thought":   {"volume_db": -3.0, "speed_factor": 0.93},  # Quieter + slower
}

def apply_speech_act_adjustments(
    audio: np.ndarray,
    sample_rate: int,
    speech_act: str,
) -> tuple[np.ndarray, int]:
    """Apply volume and speed adjustments based on speech-act type."""
    params = SPEECH_ACT_PARAMS.get(speech_act, SPEECH_ACT_PARAMS["spoken"])

    # Volume: multiply by linear gain factor
    if params["volume_db"] != 0.0:
        gain = 10 ** (params["volume_db"] / 20.0)
        audio = audio * gain
        audio = np.clip(audio, -1.0, 1.0)  # Prevent clipping

    # Speed: resample if factor != 1.0
    if params["speed_factor"] != 1.0:
        new_length = int(len(audio) / params["speed_factor"])
        audio = np.interp(
            np.linspace(0, len(audio) - 1, new_length),
            np.arange(len(audio)),
            audio,
        )

    return audio, sample_rate
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Qwen3 8B only | 14B Q4_K_M with 8B fallback | Phase 8 upgrade | Better context understanding, improved attribution accuracy |
| FP16 KV cache (default) | Q8_0 KV cache quantization | Ollama late 2024 | ~50% KV cache memory reduction with minimal quality loss |
| Regex-only dialogue detection | Hybrid regex + LLM | Phase 8 upgrade | Catches internal monologue, indirect dialogue, speech-act subtypes |
| No emotion system | Three-layer (baseline + scene + override) | Phase 8 new | Audiobook sounds emotionally appropriate per scene |
| Volume is uniform | Speech-act-based volume/speed | Phase 8 new | Whispered lines quieter, shouted louder, thoughts reflective |

**Deprecated/outdated:**
- Qwen3-TTS `instruct` parameter with cloned voices: Does NOT work (GitHub #231, #238). All emotion must be post-processing.
- Ollama default 5-minute keep_alive: Too short for multi-phase pipeline. Use keep_alive=-1.

## Open Questions

1. **Exact RAM threshold for 14B vs 8B**
   - What we know: 14B Q4_K_M needs ~10-12GB for weights + KV cache. 16GB total on target machine.
   - What's unclear: How much RAM macOS and background processes consume in practice during pipeline runs.
   - Recommendation: Start with 12GB threshold (conservative). If 14B loads but swaps, raise to 13GB. Expose as config for tuning.

2. **Speed adjustment quality at 7-8% change**
   - What we know: Small speed changes (<10%) via numpy interpolation are generally acceptable. Larger changes need proper resampling.
   - What's unclear: Whether 8% speedup for shouted lines introduces audible pitch artifacts with Qwen3-TTS output specifically.
   - Recommendation: Implement with numpy interpolation first. If artifacts are audible, switch to scipy.signal.resample for that case.

3. **Batching strategy for scene mood LLM calls**
   - What we know: One call per chapter with structured array output is the right approach (mirrors existing attribution pattern).
   - What's unclear: Whether Qwen3 14B can reliably produce structured mood annotations for 5-10 scenes in a single call within the context window.
   - Recommendation: Implement with per-chapter batching. If responses truncate, fall back to per-scene calls.

## Sources

### Primary (HIGH confidence)
- Existing codebase: `src/attribution/llm_client.py`, `src/attribution/models.py`, `src/attribution/attributor.py` — current Ollama integration patterns
- Existing codebase: `src/parser/segmenter.py` — current dialogue detection regex patterns
- Existing codebase: `src/synthesis/synthesizer.py`, `src/synthesis/models.py` — current synthesis pipeline architecture
- Ollama official docs: https://docs.ollama.com/faq — keep_alive, model management
- Ollama Python library: https://github.com/ollama/ollama-python — ps(), show(), chat() API
- Ollama KV cache quantization: https://smcleod.net/2024/12/bringing-k/v-context-quantisation-to-ollama/ — OLLAMA_KV_CACHE_TYPE configuration

### Secondary (MEDIUM confidence)
- Qwen3 14B memory requirements: https://localllm.in/blog/ollama-vram-requirements-for-local-llms — 10-12GB for Q4_K_M
- psutil memory API: https://psutil.readthedocs.io/ — virtual_memory().available on macOS
- pydub volume API: https://www.pydub.com/ — dB-based gain adjustment

### Tertiary (LOW confidence)
- Speed adjustment via numpy interpolation quality — needs empirical validation with actual Qwen3-TTS output
- Exact memory consumption of 14B + KV cache q8_0 on 16GB M-series — varies by Ollama version and macOS state

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries already in project or well-established (psutil is the only new dependency)
- Architecture: HIGH — extends existing codebase patterns, not a rewrite
- Pitfalls: HIGH — based on actual codebase analysis and documented upstream limitations
- Emotion system: MEDIUM — novel feature, but user decisions constrain design well; open question on speed adjustment quality

**Research date:** 2026-03-04
**Valid until:** 2026-04-04 (stable domain, unlikely to change rapidly)
