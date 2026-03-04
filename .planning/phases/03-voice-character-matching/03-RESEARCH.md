# Phase 3: Voice-Character Matching - Research

**Researched:** 2026-03-03
**Domain:** Voice-character matching via LibriTTS-P speaker metadata + LLM trait comparison
**Confidence:** MEDIUM

## Summary

Phase 3 matches each character from the Phase 2 character registry to a real human voice from the LibriTTS-P dataset (2,443 speakers). The primary path uses the local Qwen3 8B LLM to compare character voice traits (from `CharacterProfile.voice_qualities`) against LibriTTS-P speaker annotations (perception/impression words). When the cast exceeds what fits in a single LLM context window, sentence-transformers embedding similarity serves as an automatic fallback for remaining characters.

LibriTTS-P provides human-annotated speaker identity prompts for all 2,443 speakers in LibriTTS-R. Each speaker has comma-separated perception and impression words with intensity modifiers (e.g., "very masculine, slightly thick, cool, slightly intellectual, calm"). These annotations are stored in three annotator CSV files (`df1_en.csv`, `df2_en.csv`, `df3_en.csv`) with a simple `speaker_id|attributes` pipe-delimited format. The audio files themselves live in the LibriTTS-R dataset organized as `{split}/{speaker_id}/{chapter_id}/{speaker_id}_{chapter_id}_{utterance_id}.wav` at 24kHz sample rate — exactly what Chatterbox TTS requires for voice cloning reference clips.

**Primary recommendation:** Load LibriTTS-P speaker annotations into a local JSON index at setup time, use Qwen3 8B to match characters to speakers in batched LLM calls, fall back to sentence-transformers cosine similarity for overflow, and select the longest clean utterance per matched speaker as the reference clip path.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Balanced blend of gender, age, and vocal quality — no single factor dominates
- Distinctiveness between characters is prioritized — swap a less-perfect individual match for more contrast when two characters sound too similar
- Under-described characters: infer traits from scene context, dialogue style, and relationships (best effort)
- LLM includes brief reasoning for each assignment (e.g., "Matched because gruff, older male, authoritative tone")
- Narrator voice matches the book's tone — a dark thriller gets a lower/tense narrator, a comedy gets a lighter voice
- Narrator gender: Claude decides per book based on content and tone
- Smart narrator default: first-person novels → protagonist's voice IS the narrator; third-person → separate dedicated narrator voice
- Narrator sourced from same LibriTTS-P speaker pool as characters (not a fixed/external voice)
- CLI table printed before locking: shows character name, LibriTTS-P speaker ID, and LLM reasoning per row
- User confirms with y/n prompt before voice_map.json is written
- No interactive override — user edits voice_map.json directly, then re-runs match to validate
- Rejection flow: exit with instructions telling user to edit voice_map.json and re-run
- Major vs minor defined by dialogue line count
- Minor characters can share a voice, but never two characters who appear in the same chapter
- When speaker pool runs out of good matches: assign with a warning flag in voice_map.json so user knows which matches are weak

### Claude's Discretion
- Exact dialogue count threshold for major/minor classification (tuned per book size)
- Narrator gender selection logic per book
- Embedding similarity fallback implementation details
- Confidence scoring methodology

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| VOICE-01 | Match characters to real human voices from LibriTTS-P (2,443 speakers) | LibriTTS-P df1/df2/df3 CSV annotations provide perception+impression words per speaker; LLM compares against CharacterProfile traits |
| VOICE-02 | LLM compares character voice traits to LibriTTS-P speaker annotations to find best matches | Qwen3 8B with structured output (existing llm_client.py pattern) processes batches of speakers against character traits |
| VOICE-03 | Embedding similarity (sentence-transformers) serves as fallback for large casts | all-MiniLM-L6-v2 encodes both character trait descriptions and speaker annotations into 384-dim vectors; cosine similarity ranks matches |
| VOICE-04 | No two major characters are assigned the same voice reference | Post-matching dedup pass checks major characters (by dialogue count threshold), swaps duplicates to next-best match |
| VOICE-05 | Voice assignments saved to voice_map.json and cached for re-runs | voice_map.json written after user confirmation; re-running match phase reads existing file and skips LLM calls |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| ollama (Python) | >=0.6 | LLM calls for trait-to-speaker matching | Already in project; Qwen3 8B structured output proven in Phase 2 |
| pydantic | >=2.0 | Data models for voice map, match results | Already in project; schema validation for LLM responses |
| sentence-transformers | >=3.0 | Embedding similarity fallback | De facto standard for text embeddings; all-MiniLM-L6-v2 is 80MB, fast on CPU |
| rich | >=13.0 | CLI table display for voice assignments | Already in project; Rich tables for pre-confirmation review |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| typer | >=0.24 | CLI `match` command | Already in project; add match subcommand |
| csv (stdlib) | - | Parse LibriTTS-P annotation CSVs | df1_en.csv uses pipe delimiter, stdlib handles it |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| sentence-transformers | numpy-only cosine similarity | Avoids heavy dependency but loses pre-trained semantic understanding |
| all-MiniLM-L6-v2 | all-mpnet-base-v2 | Higher quality but 420MB vs 80MB; overkill for trait matching |
| parler-tts/libritts-r-filtered-speaker-descriptions | LibriTTS-P direct | Parler-tts only has 40 speakers in clean config; LibriTTS-P has 2,443 — must use LibriTTS-P |

**Installation:**
```bash
uv pip install sentence-transformers
```

Note: sentence-transformers pulls in torch — but Chatterbox (Phase 4) already requires torch, so no net new heavy dependency. However, Phase 3 should NOT load the full torch GPU stack; sentence-transformers runs fine on CPU for text embeddings.

## Architecture Patterns

### Recommended Project Structure
```
src/
├── matching/
│   ├── __init__.py         # Public API: run_matching()
│   ├── models.py           # VoiceAssignment, VoiceMap, SpeakerAnnotation
│   ├── speaker_index.py    # Load/parse LibriTTS-P CSVs into speaker index
│   ├── trait_matcher.py    # LLM-based trait comparison (primary path)
│   ├── embedding_matcher.py # sentence-transformers fallback
│   ├── dedup.py            # Major character uniqueness enforcement
│   └── clip_selector.py    # Select best reference audio clip per speaker
├── attribution/            # (existing Phase 2)
├── parser/                 # (existing Phase 1)
└── pipeline.py             # Add run_match() call
```

### Pattern 1: Two-Tier Matching Strategy
**What:** LLM primary path handles small-to-medium casts; embedding fallback handles overflow.
**When to use:** Always. LLM context window limits how many speakers can be evaluated per call.
**How it works:**
1. Classify characters as major/minor by dialogue line count
2. For major characters: LLM evaluates top-N candidate speakers (pre-filtered by gender/age)
3. For minor characters OR when LLM context is tight: embedding similarity ranks all speakers
4. Dedup pass ensures no two major characters share a speaker

### Pattern 2: Pre-Filtering Before LLM
**What:** Filter 2,443 speakers down to ~50-100 candidates before LLM evaluation.
**When to use:** Always — sending all 2,443 speaker annotations to the LLM is infeasible.
**Pre-filter criteria:**
1. Gender match (mandatory): character gender → speaker perception words containing "masculine"/"feminine"
2. Age range match (soft): map character age_range to speaker annotations ("adult-like", "young", "middle-aged")
3. This reduces the candidate pool to a manageable size for LLM batched evaluation

### Pattern 3: Consensus Speaker Annotations
**What:** LibriTTS-P has 3 annotators per speaker (df1, df2, df3). Merge annotations for robustness.
**When to use:** Always — single-annotator data may have bias.
**How:**
1. Load all three CSVs
2. For each speaker_id, union all perception/impression words across annotators
3. Optionally weight by agreement (word appearing in 2/3 or 3/3 annotators = higher confidence)

### Anti-Patterns to Avoid
- **Sending all 2,443 speakers to LLM at once:** Context window overflow. Pre-filter first.
- **Matching on gender alone:** Violates "balanced blend" decision. Must consider age, vocal quality, distinctiveness.
- **Ignoring co-occurrence for minor character sharing:** Two minor characters in the same chapter must NOT share a voice, even though minor characters can share generally.
- **Loading full LibriTTS-R audio at index time:** Only store metadata. Resolve audio paths lazily when writing voice_map.json.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Text similarity scoring | Custom cosine similarity on TF-IDF | sentence-transformers | Semantic understanding matters; "gruff" should match "rough, deep voice" |
| CSV parsing with pipe delimiter | Manual string splitting | csv.reader with delimiter='|' | Handles edge cases (quoted fields, encoding) |
| CLI table formatting | Print formatting with string padding | rich.table.Table | Proper column alignment, color, borders |
| Token estimation | New implementation | Existing estimate_tokens() from llm_client.py | Already proven in Phase 2; reuse |

**Key insight:** The matching problem is fundamentally a semantic similarity task — character trait descriptions need to match speaker annotations that use different vocabulary. "Low, gruff voice" should match "masculine, slightly thick, dark". This is exactly what sentence-transformers excels at, even as a fallback.

## Common Pitfalls

### Pitfall 1: LibriTTS-P Subset Confusion
**What goes wrong:** Downloading full LibriTTS-R (86GB) when only metadata is needed for matching.
**Why it happens:** LibriTTS-P annotations cover ALL speakers, but audio is stored in LibriTTS-R subsets.
**How to avoid:** Phase 3 only needs: (1) LibriTTS-P CSVs from GitHub repo (metadata only, tiny), (2) A pointer to where LibriTTS-R audio lives on disk. Audio download is a setup step, not a matching step. Recommend train-clean-360 (28GB, 904 speakers) as the default subset — good speaker diversity without the full 86GB download.
**Warning signs:** Phase 3 code trying to download audio files during matching.

### Pitfall 2: Speaker ID Type Mismatch
**What goes wrong:** LibriTTS-P CSVs store speaker_id as integer, but directory paths use string format.
**Why it happens:** CSV parsing may return strings; Path operations need exact string matching.
**How to avoid:** Normalize speaker_id to string early and consistently. Use `str(speaker_id)` everywhere.

### Pitfall 3: Narrator Assignment Edge Cases
**What goes wrong:** First-person novels assign protagonist as narrator, but protagonist may not have voice_qualities filled.
**Why it happens:** First-person narrator rarely describes their own voice in text.
**How to avoid:** For first-person narrator=protagonist, use the protagonist's character traits (personality, description) to infer voice. For third-person, select a dedicated narrator voice based on book tone analysis from chapter text.

### Pitfall 4: Embedding Model Memory on M4
**What goes wrong:** sentence-transformers loads torch with GPU support, competing with system memory.
**Why it happens:** Default torch installation enables MPS on Apple Silicon.
**How to avoid:** Force CPU device for sentence-transformers: `SentenceTransformer('all-MiniLM-L6-v2', device='cpu')`. The 384-dim embeddings for 2,443 speakers take <1MB — GPU is unnecessary.

### Pitfall 5: Chatterbox Reference Clip Quality
**What goes wrong:** Selected reference clips are too short or noisy for good voice cloning.
**Why it happens:** Not all LibriTTS-R utterances are equally clean or long enough.
**How to avoid:** Select the longest available utterance per speaker (Chatterbox recommends >=10 seconds). If the longest clip is under 5 seconds, concatenate multiple utterances. Prefer utterances from the same chapter for consistent recording conditions.

## Code Examples

### Loading LibriTTS-P Speaker Annotations
```python
import csv
from pathlib import Path

def load_speaker_annotations(data_dir: Path) -> dict[str, list[str]]:
    """Load and merge annotations from all 3 annotators."""
    merged: dict[str, set[str]] = {}

    for csv_file in ["df1_en.csv", "df2_en.csv", "df3_en.csv"]:
        path = data_dir / csv_file
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.reader(f, delimiter="|")
            for row in reader:
                if len(row) != 2:
                    continue
                speaker_id = row[0].strip()
                traits = [t.strip() for t in row[1].split(",")]
                if speaker_id not in merged:
                    merged[speaker_id] = set()
                merged[speaker_id].update(traits)

    return {sid: sorted(traits) for sid, traits in merged.items()}
```

### LLM Trait Matching (Existing Pattern)
```python
# Reuses call_llm_structured from src/attribution/llm_client.py
from src.attribution.llm_client import call_llm_structured

class VoiceMatchResult(BaseModel):
    speaker_id: str
    reasoning: str
    confidence: float

class VoiceMatchBatch(BaseModel):
    matches: list[VoiceMatchResult]

# System prompt asks LLM to match character traits to speaker annotations
result = call_llm_structured(
    system_prompt="Match each character to the best LibriTTS-P speaker...",
    user_content=f"Characters:\n{character_traits}\n\nSpeakers:\n{speaker_annotations}",
    schema_class=VoiceMatchBatch,
)
```

### Embedding Similarity Fallback
```python
from sentence_transformers import SentenceTransformer, util

model = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")

# Encode character trait description
char_desc = "gruff, low-pitched, elderly male with authoritative tone"
char_embedding = model.encode(char_desc, convert_to_tensor=True)

# Encode all speaker annotations (do once, cache)
speaker_descs = ["very masculine, slightly thick, cool, calm", ...]
speaker_embeddings = model.encode(speaker_descs, convert_to_tensor=True)

# Find best match
scores = util.cos_sim(char_embedding, speaker_embeddings)[0]
best_idx = scores.argmax().item()
```

### Reference Clip Selection
```python
def select_reference_clip(
    speaker_id: str,
    libritts_root: Path,
    min_duration_sec: float = 5.0,
) -> Path | None:
    """Select longest utterance for a speaker as Chatterbox reference clip.

    LibriTTS-R structure: {root}/{split}/{speaker_id}/{chapter_id}/{utterance}.wav
    """
    speaker_dirs = list(libritts_root.rglob(f"*/{speaker_id}"))
    if not speaker_dirs:
        return None

    best_wav = None
    best_size = 0

    for speaker_dir in speaker_dirs:
        for wav_file in speaker_dir.rglob("*.wav"):
            size = wav_file.stat().st_size
            if size > best_size:
                best_size = size
                best_wav = wav_file

    return best_wav
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Manual voice assignment | LLM trait comparison | 2024+ (LLM capabilities) | Automated matching scales to large casts |
| TF-IDF text similarity | Sentence-transformer embeddings | 2021+ | Semantic matching ("gruff" ≈ "rough, deep") |
| LibriTTS (original) | LibriTTS-R (restored audio quality) | 2023 | Cleaner reference clips for voice cloning |
| LibriTTS-R (no annotations) | LibriTTS-P (speaker identity prompts) | 2024 | Human-annotated speaker traits enable matching |

**Deprecated/outdated:**
- LibriTTS original: Use LibriTTS-R for better audio quality
- parler-tts filtered dataset: Only 40 speakers in clean config — insufficient for diverse casts

## Open Questions

1. **LibriTTS-R subset scope**
   - What we know: train-clean-100 has 247 speakers (8.1GB), train-clean-360 has 904 speakers (28GB)
   - What's unclear: Whether 904 speakers provides enough diversity for all book genres, or if train-other-500 (noisier but 500+ more speakers) is needed
   - Recommendation: Default to train-clean-360 (904 speakers). Allow user to configure LibriTTS-R root path. If a speaker from LibriTTS-P annotations isn't found in the local audio files, skip it gracefully during matching.

2. **Major/minor threshold**
   - What we know: User wants dialogue line count to define major vs minor
   - What's unclear: Exact threshold — 10 lines? 20? Percentage-based?
   - Recommendation: Default threshold of 5 dialogue lines for "major" status. Books with >20 characters may need a higher threshold. Make it configurable.

3. **LLM batch size for matching**
   - What we know: Qwen3 8B has 32K context. Each speaker annotation is ~50-100 chars. Each character profile is ~200-300 chars.
   - What's unclear: Optimal number of candidate speakers per LLM call
   - Recommendation: Pre-filter to ~30-50 candidates per character, send in a single call. If >50 candidates remain after gender/age filtering, use embedding similarity to rank top 30 before LLM evaluation.

## Sources

### Primary (HIGH confidence)
- [LibriTTS-P GitHub](https://github.com/line/LibriTTS-P) — Dataset structure, CSV format, annotation files
- [LibriTTS-P Paper (Interspeech 2024)](https://arxiv.org/html/2406.07969v1) — 2,443 speakers, perception/impression words, annotation methodology
- [LibriTTS-P Demo](https://masayakawamura.github.io/libritts-p/) — Speaker prompt examples, annotation style
- [LibriTTS-R OpenSLR](https://www.openslr.org/141/) — Audio subset sizes and download links

### Secondary (MEDIUM confidence)
- [Chatterbox GitHub](https://github.com/resemble-ai/chatterbox) — Reference clip requirements (10s+, 24kHz WAV)
- [Chatterbox Issue #39](https://github.com/resemble-ai/chatterbox/issues/39) — Audio clip guidelines for cloning
- [sentence-transformers docs](https://sbert.net/) — all-MiniLM-L6-v2 usage, cosine similarity API
- [parler-tts filtered descriptions](https://huggingface.co/datasets/parler-tts/libritts-r-filtered-speaker-descriptions) — Only 40 speakers in clean config (insufficient, confirmed)

### Tertiary (LOW confidence)
- LibriTTS-R speaker counts per subset (247/904) — from WebSearch, cross-referenced with OpenSLR page but exact counts not in official docs

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries already in project or well-established (sentence-transformers, pydantic, ollama)
- Architecture: MEDIUM — two-tier matching strategy is sound but LLM batch sizing needs empirical tuning
- Pitfalls: MEDIUM — LibriTTS-P CSV format verified via raw file fetch, but reference clip selection logic needs validation against actual audio file layout
- LibriTTS-P data format: HIGH — directly fetched and verified df1_en.csv raw content (pipe-delimited, speaker_id|comma-separated traits)

**Research date:** 2026-03-03
**Valid until:** 2026-04-03 (stable domain, no fast-moving dependencies)
