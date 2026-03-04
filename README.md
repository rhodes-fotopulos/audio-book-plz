# audio-book-plz

Convert any EPUB into a multi-voice audiobook with automatic character casting — runs 100% locally.

## What It Does

Feed it an EPUB and it produces an MP3 audiobook where each character has a distinct, automatically assigned voice:

1. **Parses** the EPUB into chapters, paragraphs, and sentences with dialogue detection
2. **Identifies speakers** using a local LLM (Ollama) — figures out who's talking on every line and builds character profiles (gender, age, voice qualities, personality)
3. **Casts voices** by matching character traits against 2,443 real human voice descriptions from the [LibriTTS-P](https://github.com/line/LibriTTS-P) dataset
4. **Synthesizes audio** with [Chatterbox TTS](https://github.com/resemble-ai/chatterbox) — clones the matched real voice for each character
5. **Assembles** everything into chapter MP3s and a final audiobook with proper pauses and normalization

## Why

Multi-voice audiobooks are a premium product that normally requires hiring voice actors. This automates the entire pipeline — from raw text to cast, voiced, and mixed audio — using only open-source models running on your own hardware.

## Requirements

- **Hardware**: Apple Silicon Mac (M1+), 16GB RAM recommended
- **Software**: Python 3.11+, Ollama, ffmpeg
- **Models**: Qwen 3 8B (via Ollama) + Chatterbox TTS (~4GB)
- **Voice data**: LibriTTS-P dataset (one-time download)

## Status

Early development — see [PLAN.md](PLAN.md) for the full architecture and implementation roadmap.

## License

MIT
