# EPUB to Audiobook — Project Plan

## Overview

A local Python app that converts EPUB files into multi-voice audiobooks (.mp3) using a local LLM for speaker attribution/character analysis and Chatterbox TTS for voice synthesis. Runs entirely on an M4 Mac with 16GB RAM.

---

## Architecture

```
┌──────────┐    ┌───────────┐    ┌──────────────┐    ┌─────────────┐    ┌──────────┐
│  EPUB    │───▶│  Parser   │───▶│  LLM Speaker │───▶│  Voice      │───▶│  Audio   │
│  Input   │    │  + Split  │    │  Attribution │    │  Synthesis  │    │  Output  │
└──────────┘    └───────────┘    └──────────────┘    └─────────────┘    └──────────┘
  .epub          ebooklib +       Ollama (Qwen 3     Chatterbox TTS      pydub →
                 BeautifulSoup    8B Q4_K_M)         (MPS GPU)           final .mp3
```

---

## Hardware Constraints (M4 Mac, 16GB Unified Memory)

Apple Silicon's unified memory architecture means the GPU shares all 16GB — no separate VRAM needed.

| Component        | RAM Usage | Device | Notes                                       |
|------------------|-----------|--------|---------------------------------------------|
| Ollama (8B Q4)   | ~5-6 GB   | GPU    | Metal-accelerated via Ollama                |
| Chatterbox TTS   | ~4 GB     | MPS    | GPU-accelerated; FFT ops fall back to CPU   |
| Python overhead  | ~1-2 GB   | CPU    | App, audio buffers, etc.                    |

**Strategy**: Run LLM and TTS in **separate phases** — never simultaneously. Unload one before loading the other. This keeps peak usage under ~10GB, well within the 16GB unified memory budget.

### MPS (Metal Performance Shaders) for Chatterbox
- Load model to CPU first, then move inference components (t3, s3gen, ve) to MPS
- Set `PYTORCH_ENABLE_MPS_FALLBACK=1` — most ops run on GPU, only `aten::_fft_r2c` falls back to CPU
- This yields **~2-3x speedup** over pure CPU (real-world reports: ~2x on Apple Silicon)
- The M4's GPU is significantly faster than M1/M2 — expect performance at the better end

---

## Phase 1: EPUB Parsing & Text Segmentation

### Goal
Extract chapter text from EPUB and split into speech-ready segments with pause hints.

### Libraries
- `ebooklib` — read EPUB2/EPUB3 files
- `beautifulsoup4` + `lxml` — strip HTML, extract paragraph/chapter structure
- `nltk` or `re` — sentence tokenization

### Design

```python
# Core data structures
@dataclass
class TextSegment:
    chapter: int
    paragraph: int
    sentence: int
    text: str
    segment_type: str  # "narration", "dialogue", "chapter_heading", "scene_break"

@dataclass
class Chapter:
    number: int
    title: str
    segments: list[TextSegment]
```

### Parsing Pipeline
1. Open EPUB with `ebooklib.epub.read_epub()`
2. Iterate spine items (`ITEM_DOCUMENT` type) — these are chapters in reading order
3. For each chapter's HTML content:
   - Parse with BeautifulSoup
   - Extract `<p>`, `<h1>`–`<h3>`, `<div>` tags
   - Detect dialogue (text within quotation marks: `"..."`, `'...'`, `"..."`)
   - Sentence-split narration blocks
4. Tag each segment with its type (narration, dialogue, heading, scene break)
5. Insert pause markers:
   - **Short pause** (0.3s): between sentences
   - **Medium pause** (0.8s): between paragraphs
   - **Long pause** (1.5s): between scenes/chapters
6. Output: ordered list of `TextSegment` objects per chapter, serialized to JSON for the next phase

### Text Chunking for TTS
Chatterbox has a ~300 character limit per generation call. Segments exceeding this get split at sentence boundaries, keeping chunks under 280 chars with a safety margin.

---

## Phase 2: LLM Speaker Attribution & Character Extraction

### Goal
Use a local LLM to identify who is speaking each dialogue line and build a character profile database.

### Setup
- **Runtime**: [Ollama](https://ollama.com) — simplest local LLM runner for Mac
- **Model**: `qwen3:8b` (Q4_K_M quantization) — best all-rounder for 16GB systems, strong instruction following
- **Alternative**: `llama3.1:8b` or `mistral:7b` if Qwen doesn't suit

### Attribution Pipeline

**Pass 1 — Character Discovery (per chapter)**

Send each chapter's text (in chunks that fit context) to the LLM with a prompt like:

```
You are analyzing a novel chapter. List every character who appears,
with these details:
- Name (and any aliases/nicknames)
- Gender
- Age (approximate)
- Voice qualities (deep, soft, raspy, young, old, accent, etc.)
- Personality traits that affect speech (shy, boisterous, formal, etc.)
- Key physical descriptions mentioned

Return as JSON.
```

Store results in a `CharacterProfile` database that accumulates across chapters:

```python
@dataclass
class CharacterProfile:
    name: str
    aliases: list[str]
    gender: str
    age_range: str
    voice_qualities: list[str]    # "deep", "raspy", "gentle", etc.
    personality: list[str]        # "formal", "brash", "timid", etc.
    description: str              # free-text summary
    voice_ref_path: str | None    # assigned later in Phase 3
```

**Pass 2 — Dialogue Attribution (per chapter)**

Send chapter text + known characters list to the LLM:

```
Given these characters: [list]
For each line of dialogue in this text, identify the speaker.
For narration, mark as "narrator".
Return as a JSON array matching the segment indices.
```

Output: each `TextSegment` now has a `speaker` field ("narrator", character name, or "unknown").

### Caching & Efficiency
- Cache LLM results to JSON files per chapter so re-runs skip completed work
- Process chapter-by-chapter to stay within context limits (~4K-8K tokens per request)
- Batch narration segments — only dialogue needs per-line attribution

---

## Phase 3: Voice Assignment via LibriTTS-P

### Goal
Automatically match each character to a real human voice from the LibriTTS-P dataset (2,443 speakers with human-annotated voice descriptions), then use that speaker's audio as Chatterbox's voice cloning reference.

### Why Real Voices
Chatterbox is a voice *cloner* — it reproduces the characteristics of a reference audio clip. Cloning from a real human recording produces more natural results than cloning from synthetic audio (which would compound artifacts). LibriTTS-P provides clean, 24kHz audiobook recordings from real LibriVox volunteers.

### LibriTTS-P Dataset

**Source**: [LibriTTS-R audio](https://www.openslr.org/141/) + [LibriTTS-P annotations](https://github.com/line/LibriTTS-P)
**License**: CC BY 4.0
**Speakers**: 2,443 real human voices with professional annotations

Each speaker has a human-written description using two word categories:
- **Perception words**: gender, pitch, vocal strength, clarity, fluency
- **Impression words**: personality/emotional qualities (calm, lively, warm, strict, etc.)
- **Intensity levels**: "slightly kind", "kind", "very kind"

Example speaker descriptions:
> *"feminine, adult-like, slightly relaxed, soft, raspy, intellectual, calm, friendly, reassuring, slightly kind, modest"*
> *"masculine, mature, tensed, clear, fluent, authoritative, calm, slightly strict, sharp"*

### Setup — One-Time Dataset Preparation

```bash
# Download LibriTTS-R audio (pick a subset to start — train-clean-100 is ~28GB)
wget https://www.openslr.org/resources/141/train-clean-100.tar.gz
tar -xzf train-clean-100.tar.gz -C ./data/libritts/

# Clone LibriTTS-P for speaker descriptions
git clone https://github.com/line/LibriTTS-P.git ./data/libritts-p/
```

Build a local index:
```python
@dataclass
class VoiceRef:
    speaker_id: str
    description: str           # "feminine, soft, raspy, calm, friendly..."
    gender: str
    traits: list[str]          # parsed individual trait words
    audio_path: str            # path to a ~10s clip from this speaker
    used_by: str | None        # which character is using this voice
```

Pre-process at setup time:
1. Parse LibriTTS-P speaker prompts CSV → extract descriptions per speaker ID
2. For each speaker, select a clean ~10-second audio clip from their recordings
3. Store as `voices/{speaker_id}/ref.wav` + `voices/index.json` (speaker_id → description + path)

### Matching Pipeline

**Step 1 — LLM-based matching** (best accuracy)

Send character profiles + a sample of voice descriptions to the LLM:

```
Here are the character voice traits extracted from the novel:
- Captain Ahab: masculine, old, deep, commanding, obsessive, weathered
- Ishmael: masculine, young, thoughtful, calm, curious

Here are available real voice descriptions from our library:
- Speaker 1247: "masculine, mature, deep, authoritative, calm, slightly strict"
- Speaker 0892: "masculine, adult-like, relaxed, clear, friendly, intellectual"
- Speaker 2103: "masculine, mature, tensed, gruff, sharp, commanding"
...

Match each character to the best-fitting speaker. Return as JSON:
{"Captain Ahab": "2103", "Ishmael": "0892"}
```

**Step 2 — Fallback: embedding similarity**

For large casts where LLM context is tight, use sentence embeddings:
```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer('all-MiniLM-L6-v2')  # tiny, runs on CPU

# Embed all 2,443 speaker descriptions once (cached)
speaker_embeddings = model.encode([v.description for v in voice_library])

# For each character, find closest voice
char_description = "deep, gruff, older male, commanding, weathered"
char_embedding = model.encode(char_description)
best_match = cosine_similarity(char_embedding, speaker_embeddings).argmax()
```

**Step 3 — Deduplication**

Ensure no two major characters share the same voice:
- After initial matching, check for conflicts
- Reassign duplicates to the next-best match
- With 2,443 speakers available, collisions are rare

### Output
- Updated `CharacterProfile` entries with `voice_ref_path` pointing to real LibriTTS-P audio
- A `voice_map.json` mapping speaker names → speaker ID + audio path
- Cached so re-runs don't repeat matching

---

## Phase 4: Audio Synthesis with Chatterbox TTS

### Goal
Generate audio for every text segment using Chatterbox, with the correct voice per speaker.

### Setup
- `pip install chatterbox-tts`
- Set `PYTORCH_ENABLE_MPS_FALLBACK=1` so unsupported ops (FFT) fall back to CPU transparently
- **Important**: Unload Ollama before starting TTS to free memory (`ollama stop`)

### Generation Pipeline

```python
import os
os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"

from chatterbox.tts import ChatterboxTTS
import torchaudio as ta
import torch

# Load to CPU first, then move to MPS (Apple Silicon GPU)
model = ChatterboxTTS.from_pretrained(device="cpu")
if torch.backends.mps.is_available():
    model.t3 = model.t3.to("mps")
    model.s3gen = model.s3gen.to("mps")
    model.ve = model.ve.to("mps")

for segment in segments:
    voice_ref = voice_map[segment.speaker]
    wav = model.generate(
        segment.text,
        audio_prompt_path=voice_ref,
        cfg_weight=0.5,      # lower (0.3) for narration pacing
        exaggeration=0.5,    # higher (0.7+) for dramatic dialogue
    )
    ta.save(f"output/{segment.id}.wav", wav, model.sr)
```

### Chunking Strategy
- Segments over 280 chars → split at sentence boundary → generate separately → concatenate
- Insert silence between segments:
  - 300ms between sentences (same speaker)
  - 800ms between paragraphs
  - 1500ms at chapter breaks
- Use `pydub` for silence insertion and concatenation

### Batch Processing

The synthesizer is designed around a **segment queue** rather than a simple loop, so batching can be added without restructuring:

```python
@dataclass
class SynthJob:
    segment_id: str
    text: str
    voice_ref_path: str
    cfg_weight: float
    exaggeration: float
    output_path: str

class Synthesizer:
    def __init__(self, model, batch_size: int = 1):
        self.model = model
        self.batch_size = batch_size  # start at 1, increase as models/hardware allow

    def process_queue(self, jobs: list[SynthJob]):
        """Process jobs in batches with checkpoint support."""
        pending = [j for j in jobs if not Path(j.output_path).exists()]

        for batch in chunked(pending, self.batch_size):
            # batch_size=1: sequential (current safe default)
            # batch_size>1: parallel generation when model supports it
            results = [self._generate_one(job) for job in batch]
            for job, wav in zip(batch, results):
                ta.save(job.output_path, wav, self.model.sr)
                self._update_progress(job.segment_id)

    def _generate_one(self, job: SynthJob):
        return self.model.generate(
            job.text,
            audio_prompt_path=job.voice_ref_path,
            cfg_weight=job.cfg_weight,
            exaggeration=job.exaggeration,
        )
```

**Why this matters:**
- `batch_size=1` is the safe default — works now, stays within 16GB
- When Chatterbox (or a successor) supports true batch inference, just increase `batch_size`
- Jobs grouped by same `voice_ref_path` avoid reloading voice embeddings between segments
- The queue naturally supports checkpoint/resume — skip any job whose output file exists

**Future batching strategies (no architecture changes needed):**
- **Same-voice batching**: Group consecutive segments from the same speaker → avoids voice ref reloading
- **Chapter-level parallelism**: If RAM allows, run 2-3 chapter workers via `multiprocessing`
- **True model batching**: When TTS models support batch `generate()`, pass multiple texts at once

### Performance Estimate (MPS GPU on M4)
- ~3-10 seconds per segment with MPS acceleration (vs 10-30s on CPU)
- A typical novel (~80,000 words, ~4000 segments) → **~3-11 hours of generation**
- The M4 GPU is faster than earlier Apple Silicon — expect the lower end of this range
- Same-voice batching alone could cut ~20-30% by avoiding redundant voice ref processing
- Process overnight with checkpoint/resume support

### Checkpoint/Resume
- Built into the queue — any job with an existing output file is skipped
- `progress.json` tracks completed segment IDs + timestamps
- Safe to kill and restart at any point — no partial state corruption

---

## Phase 5: Audio Assembly & Export

### Goal
Stitch all segment audio into chapter files and a final .mp3.

### Pipeline
1. Load all segment WAVs for a chapter (in order)
2. Insert appropriate silence gaps between segments
3. Concatenate into chapter WAV
4. Apply light normalization (consistent volume across voices)
5. Encode chapters as MP3 (via `pydub` + `ffmpeg`)
6. Optionally merge all chapters into a single .mp3 with chapter markers

### Libraries
- `pydub` — audio concatenation, silence insertion, format conversion
- `ffmpeg` (system install via `brew install ffmpeg`) — MP3 encoding backend
- Optional: `mutagen` — write ID3 tags (title, author, chapter markers)

### Output Structure
```
output/
  segments/          # individual segment WAVs (intermediate)
  chapters/
    chapter_01.mp3
    chapter_02.mp3
    ...
  full_audiobook.mp3 # combined with chapter markers
  metadata.json      # chapter timestamps, character voices used
```

---

## Project Structure

```
audio-book-plz/
  main.py                  # CLI entry point
  config.py                # settings (paths, model names, thresholds)

  epub_parser/
    __init__.py
    reader.py              # EPUB loading + HTML stripping
    segmenter.py           # text splitting + dialogue detection
    models.py              # TextSegment, Chapter dataclasses

  llm/
    __init__.py
    client.py              # Ollama API client wrapper
    attribution.py         # speaker identification prompts + parsing
    characters.py          # character extraction + profile management

  voice/
    __init__.py
    matcher.py             # character → voice reference matching (LLM + embedding)
    library.py             # LibriTTS-P index builder + speaker catalog
    setup.py               # one-time dataset download + reference clip extraction

  tts/
    __init__.py
    synthesizer.py         # Chatterbox TTS wrapper
    chunker.py             # text chunking for 300-char limit

  audio/
    __init__.py
    assembler.py           # concatenation, silence, normalization
    exporter.py            # MP3 encoding, ID3 tags

  data/
    libritts/              # LibriTTS-R audio files (downloaded once)
    libritts-p/            # LibriTTS-P speaker descriptions
  voices/                  # extracted ~10s reference clips per speaker
    index.json             # speaker_id → description + audio path
  output/                  # generated audio files
  cache/                   # LLM response cache per chapter

  requirements.txt
  README.md
```

---

## Dependencies

```
# requirements.txt
ebooklib>=0.18
beautifulsoup4>=4.12
lxml>=5.0
nltk>=3.8
chatterbox-tts>=0.1
torch>=2.0
torchaudio>=2.0
pydub>=0.25
requests>=2.31              # for Ollama HTTP API
mutagen>=1.47               # MP3 metadata/tags
sentence-transformers>=3.0  # for voice matching fallback (embedding similarity)
```

System dependencies:
```bash
brew install ffmpeg          # MP3 encoding backend for pydub
brew install ollama          # or download from ollama.com
ollama pull qwen3:8b         # download the LLM model
```

---

## CLI Interface

```bash
# Full pipeline
python main.py convert book.epub --output ./audiobook/

# Individual phases (for debugging / partial runs)
python main.py parse book.epub --output ./cache/parsed.json
python main.py analyze ./cache/parsed.json --output ./cache/attributed.json
python main.py synthesize ./cache/attributed.json --voices ./voices/ --output ./output/
python main.py assemble ./output/segments/ --output ./audiobook/

# Resume interrupted synthesis
python main.py synthesize ./cache/attributed.json --resume

# List detected characters
python main.py characters ./cache/attributed.json
```

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Chatterbox voice quality varies across segments | Inconsistent audiobook feel | Tune `cfg_weight` and `exaggeration` per voice; test with short excerpts first |
| LLM misattributes dialogue speakers | Wrong voice on lines | Allow manual corrections via JSON edit; re-run attribution for specific chapters |
| 16GB unified memory tight for both LLM + TTS | Crashes / swapping | Sequential phases — never run simultaneously; monitor with `htop` |
| Generation takes several hours | Slow iteration | Checkpoint/resume; process overnight; MPS GPU cuts time ~2-3x vs CPU |
| Voice match doesn't fit character | Immersion-breaking voices | 2,443 real voices to choose from; LLM + embedding matching; manual override via voice_map.json |
| LibriTTS-P dataset is large (~28GB for train-clean-100) | Disk space + download time | Start with smaller subset; only extract ~10s ref clips per speaker |
| MPS FFT fallback to CPU | Slight perf hit on one op | `PYTORCH_ENABLE_MPS_FALLBACK=1` handles transparently; rest runs on GPU |

---

## Implementation Order

1. **Phase 1**: EPUB parser + segmenter — get clean text out of EPUBs
2. **Phase 2**: LLM integration — character extraction + speaker attribution
3. **Phase 3**: Voice matching — map characters to voice refs
4. **Phase 4**: TTS synthesis — generate audio with Chatterbox
5. **Phase 5**: Audio assembly — stitch into final MP3
6. **Integration**: CLI that chains all phases, with progress tracking

Build and test each phase independently before wiring them together.

---

## Sources & References

- [Chatterbox TTS — GitHub](https://github.com/resemble-ai/chatterbox)
- [Chatterbox Mac Silicon fork](https://github.com/lorenjphillips/chatterbox-mac-silicon)
- [Chatterbox Apple Silicon — HuggingFace](https://huggingface.co/Jimmi42/chatterbox-tts-apple-silicon)
- [EbookLib — GitHub](https://github.com/aerkalov/ebooklib)
- [Ollama](https://ollama.com)
- [Speaker Identification Using LLMs (2025 paper)](https://aclanthology.org/2025.wnu-1.17.pdf)
- [Chatterbox TTS Server (community)](https://github.com/devnen/Chatterbox-TTS-Server)
- [LibriTTS-P — GitHub](https://github.com/line/LibriTTS-P)
- [LibriTTS-R Audio — OpenSLR](https://www.openslr.org/141/)
- [LibriTTS-P Paper](https://arxiv.org/abs/2406.07969)
- [S-VoCAL: Voice Character Attributes in Literature](https://arxiv.org/abs/2603.00958)
