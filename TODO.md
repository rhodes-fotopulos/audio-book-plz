# TODO

## Wire voice_baseline + emotions into TTS synthesis

### Problem

The pipeline extracts rich voice and emotion data but never uses it for synthesis:

1. **voice_baseline** (extracted per character): pace, tone, energy, typical_emotion, description
   - e.g. "A slow, gravelly voice with weary patience"
   - Currently extracted by the LLM and stored in characters.json but ignored by synthesis

2. **emotion.json** (scene moods + line overrides):
   - Scene mood: "this scene is tense anger, high intensity"
   - Line overrides: "but this specific line is joyful relief"
   - Currently all 61 chapters failed with Claude (errors were silently swallowed — now fixed with console logging)
   - Even when working, synthesis ignores this data entirely

3. **voice_qualities** (pitch, pace, tone, accent):
   - Used by voice matching (trait_matcher.py, embedding_matcher.py) for speaker selection
   - But voice_baseline has richer/overlapping data that could improve matching

### Current state

- **Synthesis** (`synthesizer.py`) only uses: text + reference voice clip
- **Post-processing** (`post_processor.py`) only adjusts volume/speed for speech-acts (whispered/shouted/thought)
- Qwen3-TTS supports text descriptions that influence speaking style — this is the integration point

### What needs to happen

#### 1. Use voice_baseline in voice matching
- `trait_matcher.py` and `embedding_matcher.py` already build character descriptions for matching
- voice_baseline fields (pace, tone, energy, typical_emotion) should feed into these descriptions
- This gives better speaker-to-character matching: a "sardonic, measured" character gets a voice that sounds sardonic and measured

#### 2. Feed voice_baseline to TTS as style conditioning
- Qwen3-TTS can take text descriptions that influence prosody
- voice_baseline.description (e.g. "A warm, rapid voice with cheerful energy") should be passed to the engine
- This makes each character's voice consistently styled across the whole book

#### 3. Feed scene mood to TTS
- Each segment belongs to a scene with a mood (joy/sadness/anger/fear/etc) and intensity
- This should modify how the TTS reads the segment — angry scenes read with more intensity, sad scenes slower and softer
- Could be a text prefix/instruction to Qwen3-TTS, or post-processing adjustments layered on top of speech-act adjustments

#### 4. Feed line overrides to TTS
- Line overrides flag segments where emotion sharply breaks from scene mood
- e.g. a joyful laugh in a funeral scene
- These should override the scene-level conditioning for that specific segment

### Three-layer model (as originally designed)

```
Layer 1: voice_baseline     → character's default style (consistent across book)
Layer 2: scene mood          → scene-level emotional context (varies by scene)
Layer 3: line override       → segment-level emotional spike (rare, high contrast)
```

Each layer modifies TTS output. Layer 1 is always active. Layer 2 adjusts based on scene. Layer 3 overrides when present.

## Merge voice_qualities and voice_baseline into single voice_profile

### Problem

Two overlapping fields describe character voice:
- `voice_qualities`: pitch, pace, tone, accent (used by matching)
- `voice_baseline`: pace, tone, energy, typical_emotion, description (extracted but unused)

Pace and tone are duplicated. The LLM extracts both, wasting output tokens.

### What needs to happen

Combine into a single `voice_profile` with all unique attributes:
- pitch, pace, tone, accent (from voice_qualities)
- energy, typical_emotion, description (from voice_baseline)

Then update:
- `CharacterProfile` model: replace both fields with `voice_profile`
- Extraction prompt: single voice section instead of two
- Merger: one merge function instead of two
- Voice matching (`trait_matcher.py`, `embedding_matcher.py`): use the combined field
- TTS synthesis: use the same field for style conditioning (see above TODO)

### Files involved

- Model: `src/attribution/models.py` (VoiceQualities, VoiceBaseline → VoiceProfile)
- Extraction prompt: `src/attribution/extractor.py`
- Merger: `src/attribution/merger.py` (_merge_voice_qualities)
- Matching: `src/matching/trait_matcher.py`, `src/matching/embedding_matcher.py`

---

### Files involved (voice_baseline + emotions)

- Character data: `src/attribution/models.py` (CharacterProfile.voice_baseline)
- Emotion data: `src/attribution/emotion/` (scene_mood.py, overrides.py, models.py)
- Voice matching: `src/matching/trait_matcher.py`, `src/matching/embedding_matcher.py`
- TTS engine: `src/synthesis/qwen_engine.py` (generate method needs mood/style params)
- Synthesis loop: `src/synthesis/synthesizer.py` (needs to look up emotion data per segment)
- Post-processing: `src/synthesis/post_processor.py` (currently only speech-acts)
