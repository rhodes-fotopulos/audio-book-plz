"""Core synthesis loop with multi-engine support, fallback, and resume.

Iterates segments chapter-by-chapter, generates audio via the configured
TTS engine (Qwen3-TTS or Chatterbox), handles failures with retry logic
and automatic engine fallback, saves checkpoint after every segment, and
reports progress.  Designed for overnight unattended operation.

v1.1 changes:
- Engine abstraction via ``create_engine()`` / ``TTSEngineBase``
- Qwen3-TTS as primary engine, Chatterbox as fallback
- Engine-versioned checkpoints with auto-archive on mismatch
- Sentence-boundary text chunking (500-600 chars for Qwen3, 280 for Chatterbox)
- Voice reference preparation with transcripts for improved cloning
- Per-segment Qwen3 -> Chatterbox fallback with summary reporting
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

from src.matching.models import VoiceMap
from src.synthesis.checkpoint import (
    archive_checkpoint,
    check_engine_compatibility,
    create_checkpoint,
    get_pending_segments,
    load_checkpoint,
    mark_completed,
    mark_failed,
    save_checkpoint,
    validate_checkpoint,
)
from src.synthesis.chunker import chunk_text_chatterbox, chunk_text_qwen
from src.synthesis.engine_base import AudioResult
from src.synthesis.engine_factory import create_engine
from src.synthesis.models import SegmentResult, SynthesisConfig, SynthesisStats
from src.synthesis.progress import SynthesisProgress

logger = logging.getLogger(__name__)


def _select_chunker(engine_type: str):
    """Return the appropriate text chunker for the engine type."""
    if engine_type == "qwen3":
        return chunk_text_qwen
    return chunk_text_chatterbox


def _generate_segment_audio(
    engine,
    text_chunks: list[str],
    ref_clip: str,
    ref_transcript: str | None,
    seg_type: str,
) -> AudioResult:
    """Generate audio for one or more text chunks and concatenate.

    Returns a single ``AudioResult`` combining all chunks.
    """
    if len(text_chunks) == 1:
        return engine.generate(
            text_chunks[0], ref_clip, ref_transcript, seg_type
        )

    # Generate each chunk and concatenate numpy arrays
    parts: list[np.ndarray] = []
    sample_rate = None
    total_duration = 0.0

    for chunk in text_chunks:
        result = engine.generate(chunk, ref_clip, ref_transcript, seg_type)
        parts.append(result.audio)
        sample_rate = result.sample_rate
        total_duration += result.duration_s

    combined = np.concatenate(parts)
    return AudioResult(
        audio=combined,
        sample_rate=sample_rate,
        duration_s=total_duration,
    )


def run_synthesis(
    book_dir: Path,
    voice_map: VoiceMap,
    attributed_segments: list[dict],
    config: SynthesisConfig,
    chapter: int | None = None,
    verbose: bool = False,
    libritts_root: Path | None = None,
) -> SynthesisStats:
    """Synthesise audio for all (or selected) segments.

    This is the main synthesis entry point.  It:
    1. Loads or creates an engine-versioned checkpoint for crash recovery.
    2. Checks engine compatibility and archives old checkpoints on mismatch.
    3. Prepares voice references with transcripts (if libritts_root provided).
    4. Loads the configured TTS engine (Qwen3-TTS or Chatterbox).
    5. Iterates segments chapter-by-chapter, generating audio.
    6. Falls back to Chatterbox on per-segment Qwen3 failures.
    7. Saves checkpoint after every segment.
    8. Reports progress with Rich bars and synthesis.log.

    Args:
        book_dir: Book output directory (contains voice_map.json etc.).
        voice_map: Loaded VoiceMap with character-to-speaker assignments.
        attributed_segments: List of segment dicts from attributed.json.
        config: Synthesis configuration (tuning, retries, thresholds).
        chapter: If set, only synthesise this chapter number.
        verbose: If True, show per-segment detail.
        libritts_root: Path to LibriTTS-R audio directory.  If provided,
            voice references are prepared with transcripts and SNR scoring.

    Returns:
        SynthesisStats with run-level aggregates.
    """
    wavs_dir = book_dir / "wavs"
    wavs_dir.mkdir(parents=True, exist_ok=True)

    # ---- Build voice lookup ----
    voice_lookup: dict[str, dict] = {}
    narrator_assignment = voice_map.narrator
    voice_lookup["narrator"] = {
        "clip_path": narrator_assignment.clip_path,
        "speaker_id": narrator_assignment.speaker_id,
        "transcript": None,
    }
    for assignment in voice_map.characters:
        voice_lookup[assignment.character_name] = {
            "clip_path": assignment.clip_path,
            "speaker_id": assignment.speaker_id,
            "transcript": None,
        }

    # ---- Voice reference preparation (if libritts_root available) ----
    if libritts_root is not None:
        try:
            from src.synthesis.voice_prep import prepare_all_voice_references

            voice_refs = prepare_all_voice_references(voice_map, libritts_root)
            for name, ref in voice_refs.items():
                if name in voice_lookup:
                    voice_lookup[name]["clip_path"] = ref.clip_path
                    voice_lookup[name]["transcript"] = ref.transcript
            logger.info(
                "Voice references prepared with transcripts from %s",
                libritts_root,
            )
        except Exception as exc:
            logger.warning(
                "Voice reference preparation failed — continuing without "
                "transcripts: %s",
                exc,
            )

    # ---- Filter segments ----
    segments = attributed_segments
    if chapter is not None:
        segments = [s for s in segments if s.get("chapter") == chapter]
        if not segments:
            logger.warning("No segments found for chapter %d", chapter)

    all_segment_ids = [s["id"] for s in segments]

    # ---- Group by chapter ----
    chapters: dict[int, list[dict]] = defaultdict(list)
    for seg in segments:
        chapters[seg["chapter"]].append(seg)
    chapter_numbers = sorted(chapters.keys())

    # ---- Create TTS engine ----
    engine = create_engine(config)

    # ---- Load or create checkpoint (with engine version check) ----
    existing_cp = load_checkpoint(book_dir)
    if existing_cp is not None:
        compatible, reason = check_engine_compatibility(
            existing_cp, engine.engine_name
        )
        if not compatible:
            logger.warning(
                "Engine mismatch: %s — archiving old checkpoint", reason
            )
            archive_checkpoint(book_dir)
            existing_cp = None

    if existing_cp is not None:
        cp, re_queue = validate_checkpoint(existing_cp, wavs_dir)
        if re_queue:
            logger.info("Re-queued %d segments with missing WAVs", len(re_queue))
    else:
        cp = create_checkpoint(
            voice_map.book_slug,
            len(all_segment_ids),
            config,
            engine_name=engine.engine_name,
            engine_version=engine.engine_version,
            engine_library=(
                "mlx-audio" if config.engine_type == "qwen3" else "chatterbox-tts"
            ),
        )

    pending = get_pending_segments(cp, all_segment_ids)
    skipped_cached = len(all_segment_ids) - len(pending)

    if not pending:
        logger.info("All %d segments already synthesised", len(all_segment_ids))
        total_audio = sum(
            info.get("duration_s", 0) for info in cp.get("completed", {}).values()
        )
        return SynthesisStats(
            total_segments=len(all_segment_ids),
            completed=len(all_segment_ids),
            failed=0,
            skipped_cached=skipped_cached,
            total_audio_duration_s=total_audio,
            total_wall_time_s=0.0,
            chapters_completed=len(chapter_numbers),
            total_chapters=len(chapter_numbers),
        )

    # ---- Load TTS engine ----
    engine.load_model()

    # ---- Fallback engine (lazy — only created on first Qwen3 failure) ----
    fallback_engine = None
    fallback_events: list[dict] = []

    # ---- Select text chunker ----
    chunker = _select_chunker(config.engine_type)

    # ---- Cleanup interval ----
    cleanup_interval = (
        config.mlx_cleanup_interval
        if config.engine_type == "qwen3"
        else config.cleanup_interval
    )

    # ---- Progress display ----
    progress = SynthesisProgress(
        total_chapters=len(chapter_numbers),
        total_segments=len(pending),
        wavs_dir=wavs_dir,
        verbose=verbose,
    )
    progress.start()
    progress.log_message(f"engine={engine.engine_name} type={config.engine_type}")
    progress.log_message(
        f"Total: {len(all_segment_ids)} segments, "
        f"{skipped_cached} cached, {len(pending)} to generate"
    )

    # ---- Main loop state ----
    pending_set = set(pending)
    completed_count = 0
    failed_count = 0
    total_audio_s = 0.0
    failed_segments: list[dict] = []
    restarted_once = False
    wall_start = time.monotonic()
    seg_counter = 0

    try:
        for ch_idx, ch_num in enumerate(chapter_numbers):
            ch_segs = sorted(chapters[ch_num], key=lambda s: s["id"])
            ch_title = ch_segs[0].get("chapter_title", "") if ch_segs else ""
            progress.update_chapter(ch_num, ch_title)

            for seg in ch_segs:
                seg_id = seg["id"]
                if seg_id not in pending_set:
                    continue

                # Voice lookup
                speaker = seg.get("speaker", "narrator")
                voice = voice_lookup.get(speaker, voice_lookup.get("narrator"))
                ref_clip = voice["clip_path"] if voice else ""
                ref_transcript = voice.get("transcript") if voice else None
                char_name = speaker
                seg_type = seg.get("type", "narration")

                # WAV output path
                wav_path = str(
                    wavs_dir / f"ch{ch_num:02d}" / f"seg_{seg_id:04d}.wav"
                )
                rel_wav_path = f"wavs/ch{ch_num:02d}/seg_{seg_id:04d}.wav"

                # Check for placeholder clip paths
                if ref_clip.startswith("AUDIO_DIR/"):
                    logger.warning(
                        "Placeholder clip path for %s: %s — audio quality may suffer",
                        char_name,
                        ref_clip,
                    )

                # ---- Retry loop ----
                success = False
                last_error = ""
                for attempt in range(1, config.max_retries + 1):
                    try:
                        text = seg.get("text", "")
                        text_chunks = chunker(text)

                        gen_start = time.monotonic()
                        audio_result = _generate_segment_audio(
                            engine, text_chunks, ref_clip, ref_transcript, seg_type
                        )
                        gen_time = time.monotonic() - gen_start

                        saved = engine.save_wav_atomic(audio_result, wav_path)
                        if not saved:
                            raise RuntimeError("WAV duration below minimum threshold")

                        duration = audio_result.duration_s

                        result = SegmentResult(
                            segment_id=seg_id,
                            wav_path=rel_wav_path,
                            duration_s=duration,
                            generation_time_s=gen_time,
                            character_name=char_name,
                            success=True,
                            attempts=attempt,
                        )
                        mark_completed(cp, seg_id, rel_wav_path, duration, gen_time)
                        progress.update_segment(result)
                        completed_count += 1
                        total_audio_s += duration
                        success = True
                        break

                    except Exception as exc:
                        last_error = str(exc)
                        progress.log_failure(
                            seg_id, last_error, attempt, config.max_retries
                        )

                        # Memory errors — cleanup before retry
                        if "MPS" in last_error or "OOM" in last_error.upper() or "Metal" in last_error:
                            engine.cleanup_memory()

                            # Fatal crash — try restart once
                            if attempt == config.max_retries and not restarted_once:
                                progress.log_message(
                                    f"Attempting {engine.engine_name} restart..."
                                )
                                try:
                                    engine.unload()
                                    engine.load_model()
                                    restarted_once = True
                                    try:
                                        gen_start = time.monotonic()
                                        audio_result = _generate_segment_audio(
                                            engine, text_chunks, ref_clip,
                                            ref_transcript, seg_type,
                                        )
                                        gen_time = time.monotonic() - gen_start
                                        saved = engine.save_wav_atomic(
                                            audio_result, wav_path
                                        )
                                        if saved:
                                            duration = audio_result.duration_s
                                            result = SegmentResult(
                                                segment_id=seg_id,
                                                wav_path=rel_wav_path,
                                                duration_s=duration,
                                                generation_time_s=gen_time,
                                                character_name=char_name,
                                                success=True,
                                                attempts=attempt + 1,
                                            )
                                            mark_completed(
                                                cp, seg_id, rel_wav_path,
                                                duration, gen_time,
                                            )
                                            progress.update_segment(result)
                                            completed_count += 1
                                            total_audio_s += duration
                                            success = True
                                            break
                                    except Exception as restart_exc:
                                        last_error = str(restart_exc)
                                        progress.log_message(
                                            f"Post-restart attempt failed: {last_error}"
                                        )
                                except Exception as reload_exc:
                                    progress.log_message(
                                        f"Model reload failed: {reload_exc} — exiting cleanly"
                                    )
                                    save_checkpoint(cp, book_dir)
                                    raise

                # ---- Auto-fallback: Qwen3 -> Chatterbox ----
                if (
                    not success
                    and config.engine_type == "qwen3"
                ):
                    try:
                        # Lazy-create fallback engine on first failure
                        if fallback_engine is None:
                            progress.log_message(
                                "Creating Chatterbox fallback engine..."
                            )
                            fallback_config = SynthesisConfig(
                                engine_type="chatterbox",
                                device=config.device,
                                narration_exaggeration=config.narration_exaggeration,
                                dialogue_exaggeration=config.dialogue_exaggeration,
                                cfg_weight=config.cfg_weight,
                            )
                            fallback_engine = create_engine(fallback_config)
                            fallback_engine.load_model()

                        # Re-chunk for Chatterbox (smaller chunks)
                        text = seg.get("text", "")
                        fb_chunks = chunk_text_chatterbox(text)

                        gen_start = time.monotonic()
                        audio_result = _generate_segment_audio(
                            fallback_engine, fb_chunks, ref_clip, None, seg_type
                        )
                        gen_time = time.monotonic() - gen_start

                        saved = fallback_engine.save_wav_atomic(
                            audio_result, wav_path
                        )
                        if saved:
                            duration = audio_result.duration_s
                            result = SegmentResult(
                                segment_id=seg_id,
                                wav_path=rel_wav_path,
                                duration_s=duration,
                                generation_time_s=gen_time,
                                character_name=char_name,
                                success=True,
                                attempts=config.max_retries + 1,
                            )
                            mark_completed(
                                cp, seg_id, rel_wav_path, duration, gen_time
                            )
                            progress.update_segment(result)
                            completed_count += 1
                            total_audio_s += duration
                            success = True

                            fallback_events.append({
                                "segment_id": seg_id,
                                "error": last_error,
                            })
                            progress.log_message(
                                f"Qwen3 failed seg_{seg_id:04d}, "
                                f"falling back to Chatterbox: {last_error[:80]}"
                            )

                    except Exception as fb_exc:
                        progress.log_message(
                            f"Chatterbox fallback also failed for seg_{seg_id:04d}: "
                            f"{fb_exc}"
                        )

                if not success:
                    result = SegmentResult(
                        segment_id=seg_id,
                        wav_path=rel_wav_path,
                        duration_s=0.0,
                        generation_time_s=0.0,
                        character_name=char_name,
                        success=False,
                        error=last_error,
                        attempts=config.max_retries,
                    )
                    mark_failed(cp, seg_id, last_error, config.max_retries)
                    progress.update_segment(result)
                    failed_count += 1
                    failed_segments.append(seg)

                # Save checkpoint after every segment
                save_checkpoint(cp, book_dir)
                seg_counter += 1

                # Periodic memory cleanup
                if seg_counter % cleanup_interval == 0:
                    engine.cleanup_memory()

                # Check failure threshold
                total_processed = completed_count + failed_count
                if (
                    total_processed >= 20
                    and failed_count / total_processed > config.failure_threshold
                ):
                    progress.log_message(
                        f"Failure rate {failed_count}/{total_processed} "
                        f"({failed_count / total_processed:.0%}) exceeds "
                        f"threshold ({config.failure_threshold:.0%}) — stopping"
                    )
                    save_checkpoint(cp, book_dir)
                    break

            else:
                # Chapter completed without threshold breach
                progress.complete_chapter(ch_idx + 1)
                continue
            # Threshold breach — break outer loop
            break

        # ---- End-of-run retry pass ----
        if failed_segments and failed_count / max(completed_count + failed_count, 1) <= config.failure_threshold:
            progress.log_message(f"Retrying {len(failed_segments)} failed segments...")
            for seg in failed_segments:
                seg_id = seg["id"]
                speaker = seg.get("speaker", "narrator")
                voice = voice_lookup.get(speaker, voice_lookup.get("narrator"))
                ref_clip = voice["clip_path"] if voice else ""
                ref_transcript = voice.get("transcript") if voice else None
                seg_type = seg.get("type", "narration")
                ch_num = seg["chapter"]
                wav_path = str(
                    wavs_dir / f"ch{ch_num:02d}" / f"seg_{seg_id:04d}.wav"
                )
                rel_wav_path = f"wavs/ch{ch_num:02d}/seg_{seg_id:04d}.wav"

                try:
                    text = seg.get("text", "")
                    text_chunks = chunker(text)
                    gen_start = time.monotonic()

                    audio_result = _generate_segment_audio(
                        engine, text_chunks, ref_clip, ref_transcript, seg_type
                    )
                    gen_time = time.monotonic() - gen_start
                    saved = engine.save_wav_atomic(audio_result, wav_path)
                    if saved:
                        duration = audio_result.duration_s
                        mark_completed(cp, seg_id, rel_wav_path, duration, gen_time)
                        completed_count += 1
                        failed_count -= 1
                        total_audio_s += duration
                        progress.log_message(
                            f"Retry OK: seg_{seg_id:04d} ({duration:.1f}s)"
                        )
                except Exception as exc:
                    progress.log_message(f"Retry failed: seg_{seg_id:04d} — {exc}")

            save_checkpoint(cp, book_dir)

        # ---- Fallback summary ----
        if fallback_events:
            total_segs = completed_count + failed_count
            fb_rate = len(fallback_events) / max(total_segs, 1)
            progress.log_message(
                f"Fallback summary: {len(fallback_events)} segments fell back "
                f"to Chatterbox out of {total_segs}"
            )
            if fb_rate > 0.1:
                logger.warning(
                    "High fallback rate (%.1f%%) — consider investigating "
                    "Qwen3-TTS issues",
                    fb_rate * 100,
                )

    finally:
        wall_time = time.monotonic() - wall_start

        # Build stats
        stats = SynthesisStats(
            total_segments=len(all_segment_ids),
            completed=completed_count + skipped_cached,
            failed=failed_count,
            skipped_cached=skipped_cached,
            total_audio_duration_s=total_audio_s,
            total_wall_time_s=wall_time,
            chapters_completed=len(chapter_numbers),
            total_chapters=len(chapter_numbers),
        )

        progress.show_stats(stats)
        progress.close()

        # Cleanup
        engine.unload()
        if fallback_engine is not None:
            fallback_engine.unload()

    return stats
