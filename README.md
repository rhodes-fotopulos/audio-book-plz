# Audio Book Plz

Convert EPUB books into multi-voice audiobooks on your Mac — all local, no cloud, no API keys.

## Quick Start

```bash
git clone https://github.com/yourusername/audio-book-plz.git
cd audio-book-plz
bash setup.sh
audio-book-plz convert mybook.epub
```

## Requirements

- **Apple Silicon Mac** (M1 or later)
- **macOS 13+** (Ventura or later)
- **16 GB RAM** recommended (8 GB works with smaller model)

Everything else is installed automatically by `setup.sh`.

## What Setup Installs

| Component | Purpose | Size |
|-----------|---------|------|
| Python 3.11 | Runtime | ~60 MB |
| uv | Fast package manager | ~15 MB |
| ffmpeg | Audio encoding | ~80 MB |
| Ollama | Local LLM runtime | ~200 MB |
| qwen3.5:9b | Speaker attribution model | ~6.6 GB |
| LibriTTS-P | Voice reference data (3 CSVs) | ~5 MB |
| Python packages | Project dependencies | ~2 GB |

> On machines with less than 16 GB RAM, setup installs `qwen3.5:4b` (~3.4 GB) instead.

## Commands

```bash
# Full pipeline — parse, attribute, match, synthesize, assemble
audio-book-plz convert book.epub

# System health check
audio-book-plz doctor

# Individual pipeline stages
audio-book-plz parse book.epub
audio-book-plz attribute output/book-name/
audio-book-plz match output/book-name/
audio-book-plz synthesize output/book-name/
audio-book-plz assemble output/book-name/

# Voice consistency check
audio-book-plz verify-voices output/book-name/
```

## How It Works

1. **Parse** — Extracts chapters, paragraphs, and sentences from EPUB with dialogue detection
2. **Attribute** — Local LLM (Qwen3.5 via Ollama) identifies who speaks each line and builds character profiles (gender, age, personality)
3. **Match** — Characters are matched to real human voices from the [LibriTTS-P](https://github.com/line/LibriTTS-P) dataset (2,443 annotated speakers)
4. **Synthesize** — [Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS) via MLX generates speech, cloning the matched voice for each character
5. **Assemble** — Segments are joined into chapter MP3s and a final audiobook with proper pauses, loudness normalization, and ID3 tags

## Options

| Option | Description |
|--------|-------------|
| `--output-dir` | Output directory (default: `output/`) |
| `--model` | Override Ollama model (e.g., `qwen3.5:4b`) |
| `--chapter N` | Synthesize only chapter N |
| `--dry-run` | Show estimated time/space without synthesizing |
| `--engine` | TTS engine (default: `qwen3`) |
| `--cpu` | Force CPU mode (skip MPS acceleration) |
| `--voice-threshold` | Cosine similarity threshold for voice consistency (default: 0.60) |
| `--mp3-dir` | Custom output directory for MP3 files |

## Troubleshooting

Run the built-in health check first:

```bash
audio-book-plz doctor
```

**Common fixes:**

| Problem | Solution |
|---------|----------|
| Ollama not running | `brew services start ollama` |
| No Qwen3.5 model | `ollama pull qwen3.5:9b` |
| ffmpeg not found | `brew install ffmpeg` |
| LibriTTS-P data missing | `bash setup.sh` (re-run is safe) |
| Out of memory during synthesis | Use `--cpu` flag or close other apps |
| Slow synthesis | Ensure MPS is available (Apple GPU acceleration) |

## License

MIT
