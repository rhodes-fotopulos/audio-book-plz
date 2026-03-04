---
phase: 07-tts-engine-swap
plan: 01
status: complete
commit: 1909792
---

## Summary

Created the TTS engine abstraction layer with two engine implementations (Qwen3-TTS and Chatterbox) behind a unified `TTSEngineBase` interface, plus a factory function for engine instantiation.

## Changes

### src/synthesis/engine_base.py (new)
- `AudioResult` dataclass: uniform numpy-based return type (audio, sample_rate, duration_s)
- `TTSEngineBase` ABC with abstract methods: load_model, generate, cleanup_memory, unload
- Concrete methods: save_wav_atomic (atomic write with tmp + rename), ensure_ollama_unloaded
- Properties: sample_rate, engine_name, engine_version

### src/synthesis/chatterbox_engine.py (new)
- `ChatterboxEngine(TTSEngineBase)` wrapping all existing Chatterbox logic from tts_engine.py
- generate() converts torch.Tensor to numpy via cpu().numpy()
- Late import pattern preserved for torch/torchaudio/chatterbox
- cleanup_memory() uses gc.collect() + torch.mps.empty_cache()

### src/synthesis/qwen_engine.py (new)
- `QwenTTSEngine(TTSEngineBase)` wrapping mlx-audio for Qwen3-TTS 1.7B Base
- load_model: sets MLX Metal cache limit, loads "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16"
- generate: calls model.generate(text, ref_audio, ref_text), converts mx.array to numpy
- cleanup_memory: mx.metal.clear_cache() with active/peak memory logging

### src/synthesis/engine_factory.py (new)
- `create_engine(config) -> TTSEngineBase` with lazy imports
- Routes to QwenTTSEngine or ChatterboxEngine based on config.engine_type
- Heavy dependencies (torch OR mlx) only load when selected engine is instantiated

### src/synthesis/models.py (modified)
- Added `engine_type: str = "qwen3"` (default primary engine)
- Added `mlx_cache_limit_gb: float = 4.0` for Metal cache bounding
- Added `mlx_cleanup_interval: int = 50` for periodic cache clearing

## Verification
- All imports verified: engine_base, chatterbox_engine, qwen_engine, engine_factory, models
- SynthesisConfig defaults: engine_type=qwen3, mlx_cache_limit_gb=4.0
- 134 existing tests pass with zero regressions
