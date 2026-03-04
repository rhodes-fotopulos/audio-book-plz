# Architecture Research

**Domain:** Local EPUB-to-multivoice-audiobook conversion pipeline
**Researched:** 2026-03-03
**Confidence:** HIGH (architecture derives directly from confirmed project constraints and verified library capabilities)

## Standard Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                          CLI Layer (Click)                           │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────┐  │
│  │  parse   │  │ attribute│  │  match   │  │ synthesize│  │assem-│  │
│  │ (phase1) │  │ (phase2) │  │ (phase3) │  │ (phase4) │  │ble   │  │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  └──┬───┘  │
│       │             │             │             │            │      │
│       └─────────────┴─────────────┴─────────────┴────────────┘      │
│                              run (all phases)                        │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ invokes
┌──────────────────────────────▼──────────────────────────────────────┐
│                        Pipeline Orchestrator                         │
│  Sequences phases, enforces memory budget, manages state JSON        │
└──┬──────────────┬──────────────┬──────────────┬──────────────┬──────┘
   │              │              │              │              │
   ▼              ▼              ▼              ▼              ▼
┌──────┐      ┌──────┐      ┌──────┐      ┌──────┐      ┌──────┐
│Phase │      │Phase │      │Phase │      │Phase │      │Phase │
│  1   │      │  2   │      │  3   │      │  4   │      │  5   │
│EPUB  │      │ LLM  │      │Voice │      │ TTS  │      │Audio │
│Parse │      │Attrib│      │Match │      │Synth │      │Assem │
└──┬───┘      └──┬───┘      └──┬───┘      └──┬───┘      └──┬───┘
   │              │              │              │              │
   ▼              ▼              ▼              ▼              ▼
segments      attributed     voice_map      WAV files     MP3 files
  .json         .json          .json        (per-seg)   (per-chapter
                                                         + full)
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| CLI Layer | Parse subcommands, route to phases, display progress | Click with `@click.group()` + per-phase `@group.command()` |
| Pipeline Orchestrator | Sequence phases, load/write state JSON, handle resume logic | `pipeline.py` — checks which output artifacts already exist |
| Phase 1: EPUB Parser | Extract ordered text segments with type tagging (dialogue vs. narration) | `ebooklib` + `beautifulsoup4` → `segments.json` |
| Phase 2: LLM Attributor | Extract characters, attribute each dialogue segment to a speaker | Ollama Python client with Pydantic structured output → `attributed.json` |
| Phase 3: Voice Matcher | Map each character to a LibriTTS-P speaker via trait comparison | LLM semantic match + `sentence-transformers` fallback → `voice_map.json` |
| Phase 4: TTS Synthesizer | Synthesize audio for each segment using Chatterbox with voice cloning | `chatterbox` per-segment with 280-char chunking → WAV files |
| Phase 5: Audio Assembler | Concatenate segment WAVs into chapter MP3s and full audiobook | `pydub` + `ffmpeg` → chapter MP3s + `audiobook.mp3` |
| State Store | JSON files on disk as durable intermediate artifacts | File-per-phase pattern; presence = completed |

## Recommended Project Structure

```
audio-book-plz/
├── audiobook/                  # Main package
│   ├── __init__.py
│   ├── cli.py                  # Click entry point — all subcommands
│   ├── pipeline.py             # Orchestrator: sequences phases, resume logic
│   │
│   ├── phases/                 # One module per pipeline phase
│   │   ├── __init__.py
│   │   ├── epub_parser.py      # Phase 1: EPUB → segments.json
│   │   ├── llm_attributor.py   # Phase 2: segments.json → attributed.json
│   │   ├── voice_matcher.py    # Phase 3: attributed.json → voice_map.json
│   │   ├── tts_synthesizer.py  # Phase 4: attributed.json + voice_map.json → WAVs
│   │   └── audio_assembler.py  # Phase 5: WAVs → chapter MP3s + audiobook.mp3
│   │
│   ├── models/                 # Pydantic schemas for intermediate state
│   │   ├── __init__.py
│   │   ├── segment.py          # Segment, SegmentType (DIALOGUE/NARRATION)
│   │   ├── character.py        # Character profile schema
│   │   └── voice_assignment.py # VoiceMap schema
│   │
│   └── utils/
│       ├── __init__.py
│       ├── text_chunker.py     # Splits text at sentence boundaries ≤280 chars
│       ├── audio_utils.py      # WAV/MP3 helpers, silence generation
│       └── memory.py           # torch.mps.empty_cache(), gc.collect() helpers
│
├── data/
│   └── libritts_p/             # LibriTTS-P CSVs (metadata + speaker annotations)
│       ├── metadata_w_style_prompt_tags.csv
│       └── speaker_descriptions.csv   # Pre-processed speaker trait index
│
├── output/                     # Per-book output directory (git-ignored)
│   └── {book_slug}/
│       ├── segments.json       # Phase 1 output
│       ├── attributed.json     # Phase 2 output
│       ├── voice_map.json      # Phase 3 output
│       ├── wavs/               # Phase 4 output
│       │   └── {seg_id:05d}_{speaker}.wav
│       ├── chapters/           # Phase 5 intermediate
│       │   └── chapter_{n:03d}.mp3
│       └── audiobook.mp3       # Phase 5 final output
│
├── pyproject.toml
└── README.md
```

### Structure Rationale

- **phases/:** One file per pipeline phase so each phase can be developed, tested, and run independently. Changes to TTS logic don't touch parsing logic.
- **models/:** Pydantic schemas shared across phases enforce the contract between phases without tight coupling. Phase 1 writes what Phase 2 reads — the schema is the interface.
- **output/{book_slug}/:** Namespaced by book so multiple books can be processed without collisions. Presence of a phase output file is the checkpoint signal.
- **data/libritts_p/:** Separate from code; the CSV index is read-only at runtime. Pre-processing into a fast lookup structure (e.g., pandas DataFrame cached at startup) avoids repeated file I/O during voice matching.

## Architectural Patterns

### Pattern 1: File-Presence Checkpointing

**What:** Each phase writes a single JSON artifact to `output/{book}/`. Before running a phase, the orchestrator checks whether that file already exists. If it does, the phase is skipped and its artifact is loaded instead.

**When to use:** Any long-running batch pipeline where individual phases take minutes to hours. Trivially resumable after crash, power loss, or deliberate interruption.

**Trade-offs:** Simple, zero external dependencies. No partial-phase recovery — if TTS is killed mid-segment, Phase 4 restarts from segment 0. Mitigated by WAV-level checkpointing within Phase 4 (see Pattern 2).

**Example:**
```python
def run_phase2(book_dir: Path, segments: list[Segment]) -> list[AttributedSegment]:
    output_path = book_dir / "attributed.json"
    if output_path.exists():
        return [AttributedSegment.model_validate(s)
                for s in json.loads(output_path.read_text())]
    result = _run_attribution(segments)
    output_path.write_text(json.dumps([s.model_dump() for s in result]))
    return result
```

### Pattern 2: Per-Segment WAV Checkpointing (Within Phase 4)

**What:** Phase 4 (TTS) writes each segment's audio as an individually named WAV file before moving to the next. On resume, it scans the `wavs/` directory and skips any segment whose WAV already exists.

**When to use:** The slowest phase (~3-10 seconds per segment, thousands of segments). This is the only phase where per-item checkpointing pays off — a 3-hour synthesis run can resume at the segment that was in-flight when it crashed.

**Trade-offs:** High disk use (~5-15MB per WAV before MP3 encoding). Naming must be deterministic — use zero-padded segment index (`{seg_id:05d}`) so file presence maps unambiguously to segment completion.

**Example:**
```python
def synthesize_segment(seg_id: int, text: str, voice_ref: Path, out_dir: Path) -> Path:
    wav_path = out_dir / f"{seg_id:05d}_{speaker_id}.wav"
    if wav_path.exists():
        return wav_path  # already done
    chunks = split_at_sentence_boundaries(text, max_chars=280)
    audio_parts = [model.generate(chunk, audio_prompt_path=str(voice_ref))
                   for chunk in chunks]
    combined = concatenate_audio(audio_parts, sample_rate=24000)
    torchaudio.save(str(wav_path), combined, 24000)
    return wav_path
```

### Pattern 3: Sequential Memory-Phase Isolation

**What:** LLM (Ollama/Qwen 3 8B, ~5-6GB) and TTS (Chatterbox, ~4GB) never run in the same process at the same time. Phase 2 and Phase 3 complete and exit before Phase 4 loads the TTS model. After Phase 4, `torch.mps.empty_cache()` + `gc.collect()` are called before Phase 5.

**When to use:** Mandatory on 16GB unified memory systems where LLM + TTS combined would exceed 10GB and cause swapping or OOM.

**Trade-offs:** No parallelism across phases. Each phase must fully complete before the next starts — this is acceptable because the pipeline runs overnight anyway.

**Example:**
```python
def run_pipeline(book_dir: Path, epub_path: Path):
    # Phase 2: LLM phase — Ollama is queried via HTTP, stays in its own process
    attributed = run_phase2(book_dir, segments)

    # Phase 3: Voice matching — sentence-transformers model is small (~100MB)
    voice_map = run_phase3(book_dir, attributed)

    # Phase 4: Load TTS model ONLY after LLM work is done
    model = ChatterboxTTS.from_pretrained(device="mps")
    wavs = run_phase4(book_dir, attributed, voice_map, model)

    # Unload TTS before assembly
    del model
    gc.collect()
    torch.mps.empty_cache()

    # Phase 5: Pure pydub/ffmpeg — no GPU needed
    run_phase5(book_dir, wavs)
```

### Pattern 4: Pydantic as Inter-Phase Contract

**What:** Define each intermediate artifact as a Pydantic model. Phases serialize to JSON via `.model_dump()` and deserialize via `.model_validate()`. No raw dict passing between phases.

**When to use:** Everywhere. It catches schema drift early (when you change Phase 1 output but forget to update Phase 2 input parsing), provides free validation, and makes the data contract explicit.

**Trade-offs:** Minor overhead. The alternative — raw dicts — causes silent bugs that are only discovered during Phase 4 or 5.

**Example:**
```python
class Segment(BaseModel):
    seg_id: int
    chapter: int
    text: str
    segment_type: Literal["DIALOGUE", "NARRATION"]
    speaker_hint: str | None = None  # from HTML tags like <em> or attribution

class AttributedSegment(Segment):
    speaker: str  # character name or "NARRATOR"
    confidence: float
```

## Data Flow

### Full Pipeline Flow

```
EPUB file
    │
    ▼ Phase 1 (ebooklib + bs4)
segments.json
  [seg_id, chapter, text, type, speaker_hint]
    │
    ▼ Phase 2 (Ollama HTTP → Qwen 3 8B → Pydantic)
attributed.json
  [seg_id, chapter, text, type, speaker, confidence]
  + characters.json [name, gender, pitch, age, traits]
    │
    ▼ Phase 3 (LLM trait compare + sentence-transformers fallback)
voice_map.json
  {character_name: {spk_id, ref_wav_path, libritts_speaker_desc}}
    │
    ├── attributed.json (re-read)
    ▼ Phase 4 (Chatterbox TTS on MPS, per-segment WAV)
wavs/
  00001_narrator.wav
  00002_hermione.wav
  ...
    │
    ▼ Phase 5 (pydub concatenation + ffmpeg MP3 encode)
chapters/
  chapter_001.mp3
  chapter_002.mp3
  ...
audiobook.mp3
```

### LLM Interaction Flow (Phase 2)

```
attributed.json ← exists? → SKIP Phase 2
    │ no
    ▼
For each chapter (batched to fit context window):
    Ollama HTTP POST /api/chat
        model: qwen3:8b
        format: AttributedSegment JSON schema
        messages: [system: speaker attribution prompt,
                   user: chapter text with segments]
    ↓
    Pydantic validate_json()
    ↓
    Write to attributed.json (atomic: write temp → rename)
```

### Voice Matching Flow (Phase 3)

```
characters.json (from Phase 2)
    │
    ▼
For each character:
    1. LLM call: "Given character traits X, which LibriTTS-P speaker
                  description best matches? Return spk_id."
       (LibriTTS-P speaker descriptions indexed in-memory from CSV)
    │
    ├── Success: use LLM-selected spk_id
    │
    └── Fallback (large cast, LLM uncertain):
        sentence-transformers encode(character_traits)
        cosine_similarity vs. pre-encoded speaker_descriptions
        top-1 match → spk_id
    │
    ▼
For each selected spk_id:
    Locate reference WAV from LibriTTS-P train-clean-100/
    (pick ~10s clean single-speaker utterance)
    │
    ▼
voice_map.json written
```

### TTS Synthesis Flow (Phase 4)

```
For each segment in attributed.json:
    │
    ├── WAV already exists? → skip
    │
    └── text length ≤ 280 chars?
        ├── YES: single Chatterbox generate() call
        └── NO: split at sentence boundaries into chunks ≤ 280 chars
                → N generate() calls
                → concatenate audio tensors
    │
    ▼
torchaudio.save(wav_path, audio, sample_rate=24000)
```

## Scaling Considerations

This is a single-user local tool; scaling to users is not applicable. Relevant "scale" is novel length (text volume) and voice cast size.

| Scale | Concern | Approach |
|-------|---------|----------|
| Short story (~5K segments) | Fits in a single session | Run all phases sequentially; no special handling needed |
| Novel (~80K words, ~4K segments) | Phase 4 takes 3-11 hours | Overnight run with per-segment WAV checkpointing; progress bar on synthesizer |
| Large cast (50+ characters) | LLM voice matching context length | Batch characters in groups of 10; use embedding fallback for remainder |
| Very long chapters | LLM context window | Split chapter into ~3K token windows; overlap by one paragraph for attribution continuity |

### Bottleneck Order

1. **First bottleneck: Phase 4 (TTS synthesis)** — 3-10 seconds per segment at 4K segments = 3-11 hours. No way to speed this up significantly on a single M4 Mac. WAV checkpointing is the mitigation.
2. **Second bottleneck: Phase 2 (LLM attribution)** — each Ollama call takes 2-8 seconds. Batching multiple segments per call (a full chapter at once) dramatically reduces round-trips. Target: 1 LLM call per chapter, not 1 per segment.
3. **Third bottleneck: Phase 3 (voice matching)** — fast if using embedding similarity on pre-indexed CSV. Slow only if making 50+ individual LLM calls. Use batch LLM call for entire cast.

## Anti-Patterns

### Anti-Pattern 1: One LLM Call Per Segment in Phase 2

**What people do:** Loop over segments and call Ollama for each individual segment to identify the speaker.

**Why it's wrong:** At 2-8 seconds per call and ~4K segments, Phase 2 takes 8K-32K seconds (2-9 hours) — nearly as long as TTS synthesis, for a task that should take minutes. The LLM has no context across segments and makes worse attribution decisions.

**Do this instead:** Send an entire chapter (or large window) of segments to the LLM in one call. Ask it to return attribution for all segments in the window as a JSON array. This gives the model full dialogue context and reduces LLM calls from ~4K to ~30 (one per chapter).

### Anti-Pattern 2: Loading TTS Model Inside the Synthesis Loop

**What people do:** Load `ChatterboxTTS.from_pretrained()` inside the per-segment loop, or reload it on every resume.

**Why it's wrong:** Model loading takes 5-15 seconds and consumes a one-time memory spike. Loading per-segment wastes minutes. Reloading on every resume adds unnecessary overhead.

**Do this instead:** Load the model once before the segment loop. Pass the loaded model instance into the synthesis function. On resume, load once, then skip already-completed segments by WAV file presence check.

### Anti-Pattern 3: Concatenating All WAVs in Memory (Phase 5)

**What people do:** Load all segment WAVs into `pydub.AudioSegment` objects and concatenate them in memory before encoding.

**Why it's wrong:** A 10-hour audiobook at 24kHz mono = ~8GB of raw PCM in memory. This will OOM on a 16GB system.

**Do this instead:** Concatenate chapter-by-chapter. Write each chapter MP3 to disk, free the audio data, then move to the next chapter. Use ffmpeg directly (via subprocess) to concatenate the chapter MP3s into the final audiobook — ffmpeg handles this without loading all audio into memory simultaneously.

### Anti-Pattern 4: Ad-Hoc Dict-Based State Passing Between Phases

**What people do:** Return raw Python dicts from phases and access keys like `segment["speaker"]` downstream.

**Why it's wrong:** A typo in a key name, an added field in Phase 1 that Phase 2 doesn't know about, or a type mismatch (speaker as `None` vs. `"NARRATOR"`) causes silent errors that surface as broken audio only in Phase 5.

**Do this instead:** Define Pydantic models for every intermediate artifact. Deserialize at phase boundaries with `model_validate()`. The schema is the interface — if Phase 1's output doesn't match Phase 2's expected input schema, you get a loud error immediately.

### Anti-Pattern 5: Raw String Segment IDs for WAV File Naming

**What people do:** Name WAV files `{speaker}_{sentence}.wav` using speaker name and partial text.

**Why it's wrong:** Speaker names may contain spaces or special characters. Partial text is non-deterministic if text changes. You can't reliably detect which segments are completed on resume.

**Do this instead:** Name WAV files by zero-padded integer segment ID: `{seg_id:05d}_{speaker_slug}.wav` where `speaker_slug` is the character name lowercased and spaces replaced with underscores. Segment ID is assigned once in Phase 1 and never changes.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| Ollama (local HTTP server) | `ollama` Python client → `ollama.chat()` with `format=` JSON schema | Ollama must be running before Phase 2/3; not started by the app |
| Chatterbox TTS (local model) | `ChatterboxTTS.from_pretrained(device="mps")` + `.generate(text, audio_prompt_path=)` | Loaded once per Phase 4 run; device="mps" with CPU fallback for FFT ops |
| ffmpeg (system binary) | `pydub` calls ffmpeg automatically for MP3 encoding; subprocess for chapter concat | Must be in PATH; `pydub.AudioSegment.converter` can be configured explicitly |
| LibriTTS-P (local files) | Read-only CSV metadata at Phase 3 startup; WAV files looked up by speaker ID | Assumes fixed directory layout from official dataset download |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| CLI → Orchestrator | Direct function call with parsed args | CLI handles argument parsing and output formatting only |
| Orchestrator → Phase N | Function call returning typed artifact list | Orchestrator decides whether to call based on artifact file presence |
| Phase 1 → Phase 2 | `segments.json` (Segment schema) | File on disk; Phase 2 reads fresh each invocation |
| Phase 2 → Phase 3 | `attributed.json` + `characters.json` | Phase 3 needs only character profiles, not full attributed segments |
| Phase 3 → Phase 4 | `voice_map.json` (character → ref WAV path) | Smallest artifact; must resolve to absolute paths for Chatterbox |
| Phase 4 → Phase 5 | `wavs/` directory (WAV files) | Phase 5 discovers WAVs by sorted seg_id filename; no manifest needed |

## Sources

- Chatterbox TTS GitHub — voice cloning API and reference audio requirements: https://github.com/resemble-ai/chatterbox
- Chatterbox TTS Server — chunking strategy for audiobook-scale text: https://github.com/devnen/Chatterbox-TTS-Server
- LibriTTS-P GitHub — speaker annotation CSV structure and speaker ID format: https://github.com/line/LibriTTS-P
- Ollama Structured Outputs — Pydantic + `format=` parameter API: https://docs.ollama.com/capabilities/structured-outputs
- LangGraph TTS Architecture — per-segment checkpointing and resumable pipeline patterns: https://vadim.blog/2026/01/18/langgraph-tts-therapeutic-audio-architecture
- PyTorch MPS memory management — `torch.mps.empty_cache()` for inter-phase GPU memory release: https://docs.pytorch.org/docs/stable/notes/mps.html
- pydub GitHub — AudioSegment concatenation and ffmpeg integration: https://github.com/jiaaro/pydub
- epub_to_audiobook — chapter-based processing and pipeline structure reference: https://github.com/p0n1/epub_to_audiobook
- Sentence Transformers — cosine similarity for voice trait matching fallback: https://sbert.net/docs/sentence_transformer/usage/semantic_textual_similarity.html

---
*Architecture research for: Local EPUB-to-multivoice-audiobook pipeline*
*Researched: 2026-03-03*
