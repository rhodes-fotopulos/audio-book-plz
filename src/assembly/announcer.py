"""Chapter announcement WAV generation using Chatterbox TTS.

Generates "Chapter N: Title" WAVs using the narrator's voice reference
from the voice map.  Uses low exaggeration (0.2) for a neutral narrator
tone.  Resume-safe: skips already-generated announcements.

Heavy imports (torch, chatterbox) are deferred until generate_announcements()
is called, following the Phase 4 late-import pattern.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def generate_announcements(
    chapters: list[dict],
    narrator_ref_path: Path,
    output_dir: Path,
    device: str = "auto",
) -> dict[int, Path]:
    """Generate chapter announcement WAVs using the narrator voice.

    For each chapter, synthesizes "Chapter N: Title" (or just "Chapter N"
    if no title) using Chatterbox TTS with the narrator's reference clip.
    Skips chapters whose announcement WAV already exists (resume-safe).

    Args:
        chapters: List of dicts with 'chapter_num' and 'title' keys.
        narrator_ref_path: Path to the narrator's reference audio clip
            from voice_map.json.
        output_dir: Directory to write announcement WAVs to.
        device: Device for TTS ('auto', 'mps', 'cpu').

    Returns:
        Dict mapping chapter_num -> Path to announcement WAV file.

    Returns:
        Empty dict if narrator reference clip is placeholder or missing.
    """
    # Check for known placeholder pattern (from matching without --libritts-audio)
    if str(narrator_ref_path).startswith("AUDIO_DIR/") or not narrator_ref_path.exists():
        logger.warning(
            "Narrator reference clip not found: %s — skipping chapter announcements. "
            "Provide --libritts-audio to enable announcements.",
            narrator_ref_path,
        )
        return {}

    output_dir.mkdir(parents=True, exist_ok=True)

    # Check which announcements already exist (resume-safe)
    announcements: dict[int, Path] = {}
    chapters_to_generate: list[dict] = []

    for ch in chapters:
        num = ch["chapter_num"]
        wav_path = output_dir / f"announce_ch{num:03d}.wav"
        if wav_path.exists():
            logger.info("Announcement for chapter %d already exists — skipping", num)
            announcements[num] = wav_path
        else:
            chapters_to_generate.append(ch)

    if not chapters_to_generate:
        logger.info("All %d announcements already exist", len(chapters))
        return announcements

    # Late imports to defer torch/chatterbox loading
    from src.synthesis.models import SynthesisConfig
    from src.synthesis.tts_engine import TTSEngine

    config = SynthesisConfig(device=device)
    engine = TTSEngine(config)

    try:
        engine.load_model()
        logger.info(
            "Generating %d chapter announcement(s)...", len(chapters_to_generate)
        )

        for ch in chapters_to_generate:
            num = ch["chapter_num"]
            title = ch.get("title", "")

            # Format announcement text
            if title:
                text = f"Chapter {num}: {title}"
            else:
                text = f"Chapter {num}"

            wav_path = output_dir / f"announce_ch{num:03d}.wav"
            logger.info("Generating: %s", text)

            # Generate with low exaggeration for neutral narrator tone
            wav_tensor = engine.generate(
                text,
                ref_clip_path=str(narrator_ref_path),
                segment_type="narration",
                exaggeration=0.2,
                cfg_weight=0.3,
            )

            # Atomic write: .tmp then rename (same pattern as Phase 4)
            tmp_path = str(wav_path) + ".tmp"
            import torchaudio

            torchaudio.save(tmp_path, wav_tensor, engine.sample_rate)
            os.rename(tmp_path, str(wav_path))

            announcements[num] = wav_path
            logger.info("Saved: %s", wav_path)

    finally:
        # Always clean up TTS model to free memory
        engine.unload()
        logger.info("TTS engine unloaded after announcement generation")

    return announcements
