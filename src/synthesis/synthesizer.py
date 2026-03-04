"""Core synthesis loop with retry, failure threshold, and resume.

Iterates segments chapter-by-chapter, generates audio via TTSEngine,
handles failures with retry logic, saves checkpoint after every segment,
and reports progress.  Designed for overnight unattended operation.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from pathlib import Path

from src.matching.models import VoiceMap
from src.synthesis.checkpoint import (
    create_checkpoint,
    get_pending_segments,
    load_checkpoint,
    mark_completed,
    mark_failed,
    save_checkpoint,
    validate_checkpoint,
)
from src.synthesis.models import SegmentResult, SynthesisConfig, SynthesisStats
from src.synthesis.progress import SynthesisProgress
from src.synthesis.tts_engine import TTSEngine

logger = logging.getLogger(__name__)


def _split_long_text(text: str, max_chars: int = 280) -> list[str]:
    """Split oversized text at sentence boundaries.

    Uses NLTK's sent_tokenize for reliable sentence splitting.
    Returns the original text as a single-element list if it fits.
    """
    if len(text) <= max_chars:
        return [text]

    from nltk.tokenize import sent_tokenize

    sentences = sent_tokenize(text)
    chunks: list[str] = []
    current = ""

    for sentence in sentences:
        if current and len(current) + len(sentence) + 1 > max_chars:
            chunks.append(current.strip())
            current = sentence
        else:
            current = f"{current} {sentence}" if current else sentence

    if current.strip():
        chunks.append(current.strip())

    return chunks if chunks else [text]


def run_synthesis(
    book_dir: Path,
    voice_map: VoiceMap,
    attributed_segments: list[dict],
    config: SynthesisConfig,
    chapter: int | None = None,
    verbose: bool = False,
) -> SynthesisStats:
    """Synthesise audio for all (or selected) segments.

    This is the main synthesis entry point.  It:
    1. Loads or creates a checkpoint for crash recovery.
    2. Filters segments by chapter if requested.
    3. Loads the TTS engine with MPS support.
    4. Iterates segments chapter-by-chapter, generating audio.
    5. Retries failed segments, then does an end-of-run retry pass.
    6. Saves checkpoint after every segment.
    7. Reports progress with Rich bars and synthesis.log.

    Args:
        book_dir: Book output directory (contains voice_map.json etc.).
        voice_map: Loaded VoiceMap with character-to-speaker assignments.
        attributed_segments: List of segment dicts from attributed.json.
        config: Synthesis configuration (tuning, retries, thresholds).
        chapter: If set, only synthesise this chapter number.
        verbose: If True, show per-segment detail.

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
    }
    for assignment in voice_map.characters:
        voice_lookup[assignment.character_name] = {
            "clip_path": assignment.clip_path,
            "speaker_id": assignment.speaker_id,
        }

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

    # ---- Load or create checkpoint ----
    existing_cp = load_checkpoint(book_dir)
    if existing_cp is not None:
        cp, re_queue = validate_checkpoint(existing_cp, wavs_dir)
        if re_queue:
            logger.info("Re-queued %d segments with missing WAVs", len(re_queue))
    else:
        cp = create_checkpoint(voice_map.book_slug, len(all_segment_ids), config)

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
    engine = TTSEngine(config)
    engine.load_model()

    # ---- Progress display ----
    progress = SynthesisProgress(
        total_chapters=len(chapter_numbers),
        total_segments=len(pending),
        wavs_dir=wavs_dir,
        verbose=verbose,
    )
    progress.start()
    progress.log_message(f"device={engine.device} model=chatterbox-500m")
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
                        # Split long text if needed
                        text = seg.get("text", "")
                        text_chunks = _split_long_text(text)

                        gen_start = time.monotonic()

                        if len(text_chunks) == 1:
                            wav = engine.generate(
                                text_chunks[0], ref_clip, seg_type
                            )
                        else:
                            # Generate each chunk and concatenate
                            import torch

                            parts = []
                            for chunk in text_chunks:
                                part = engine.generate(chunk, ref_clip, seg_type)
                                parts.append(part)
                            wav = torch.cat(parts, dim=-1)

                        gen_time = time.monotonic() - gen_start

                        saved = engine.save_wav_atomic(wav, wav_path)
                        if not saved:
                            raise RuntimeError("WAV duration below minimum threshold")

                        duration = wav.shape[-1] / engine.sample_rate

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

                        # MPS/GPU errors — cleanup before retry
                        if "MPS" in last_error or "OOM" in last_error.upper():
                            engine.cleanup_memory()

                            # Fatal GPU crash — try restart once
                            if attempt == config.max_retries and not restarted_once:
                                progress.log_message(
                                    "Attempting Chatterbox restart..."
                                )
                                try:
                                    engine.unload()
                                    engine.load_model()
                                    restarted_once = True
                                    # Give one more attempt after restart
                                    try:
                                        gen_start = time.monotonic()
                                        wav = engine.generate(
                                            text_chunks[0]
                                            if len(text_chunks) == 1
                                            else text,
                                            ref_clip,
                                            seg_type,
                                        )
                                        gen_time = time.monotonic() - gen_start
                                        saved = engine.save_wav_atomic(wav, wav_path)
                                        if saved:
                                            duration = wav.shape[-1] / engine.sample_rate
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
                                                cp, seg_id, rel_wav_path, duration, gen_time
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
                                    # Cannot continue without model
                                    raise

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
                if seg_counter % config.cleanup_interval == 0:
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
                seg_type = seg.get("type", "narration")
                ch_num = seg["chapter"]
                wav_path = str(
                    wavs_dir / f"ch{ch_num:02d}" / f"seg_{seg_id:04d}.wav"
                )
                rel_wav_path = f"wavs/ch{ch_num:02d}/seg_{seg_id:04d}.wav"

                try:
                    text = seg.get("text", "")
                    text_chunks = _split_long_text(text)
                    gen_start = time.monotonic()

                    if len(text_chunks) == 1:
                        wav = engine.generate(text_chunks[0], ref_clip, seg_type)
                    else:
                        import torch
                        parts = [engine.generate(c, ref_clip, seg_type) for c in text_chunks]
                        wav = torch.cat(parts, dim=-1)

                    gen_time = time.monotonic() - gen_start
                    saved = engine.save_wav_atomic(wav, wav_path)
                    if saved:
                        duration = wav.shape[-1] / engine.sample_rate
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

    return stats
