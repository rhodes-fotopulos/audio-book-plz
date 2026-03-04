"""Voice consistency verification with Resemblyzer speaker embeddings.

Compares every synthesized segment's speaker embedding against its
character's reference voice and regenerates outliers.  Uses the GE2E
(Generalized End-to-End) voice encoder from Resemblyzer to produce
256-dimensional speaker embeddings.

Phase 9 upgrade: prevents voice drift within a character across
thousands of segments.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from src.matching.models import VoiceMap
from src.synthesis.models import SynthesisConfig

logger = logging.getLogger(__name__)

# Placeholder prefix for clips that don't exist on disk yet
_PLACEHOLDER_PREFIX = "AUDIO_DIR/"


# ---------------------------------------------------------------------------
# Consistency report
# ---------------------------------------------------------------------------


@dataclass
class ConsistencyReport:
    """Accumulates voice consistency check results for reporting."""

    segments_checked: int = 0
    segments_passed: int = 0
    segments_regenerated: int = 0
    segments_flagged: list[dict] = field(default_factory=list)
    segments_skipped: int = 0

    def add_result(
        self,
        seg_id: int,
        speaker: str,
        similarity: float,
        passed: bool,
        regenerated: bool = False,
        attempt: int = 1,
    ) -> None:
        """Record a segment check result."""
        self.segments_checked += 1
        if passed:
            self.segments_passed += 1
        if regenerated:
            self.segments_regenerated += 1

    def add_flagged(
        self,
        seg_id: int,
        speaker: str,
        best_similarity: float,
        wav_path: str,
    ) -> None:
        """Record a segment that failed all regeneration attempts."""
        self.segments_flagged.append({
            "segment_id": seg_id,
            "speaker": speaker,
            "best_similarity": best_similarity,
            "wav_path": wav_path,
        })

    def add_skipped(self) -> None:
        """Record a skipped segment (too short or missing)."""
        self.segments_skipped += 1

    def write_report(self, output_path: Path) -> None:
        """Write JSON report with summary stats and flagged segments."""
        report = {
            "summary": {
                "segments_checked": self.segments_checked,
                "segments_passed": self.segments_passed,
                "segments_regenerated": self.segments_regenerated,
                "segments_flagged": len(self.segments_flagged),
                "segments_skipped": self.segments_skipped,
            },
            "flagged_segments": self.segments_flagged,
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        logger.info("Voice consistency report written to %s", output_path)


# ---------------------------------------------------------------------------
# Voice consistency verifier
# ---------------------------------------------------------------------------


class VoiceConsistencyVerifier:
    """Compares segment speaker embeddings against character references.

    Uses Resemblyzer's GE2E voice encoder to produce 256-dimensional
    speaker embeddings.  Segments below the cosine similarity threshold
    can trigger TTS regeneration.

    Args:
        threshold: Cosine similarity threshold (0.0-1.0).
        max_regen: Maximum regeneration attempts per segment.
        min_duration_s: Minimum segment duration for reliable embeddings.
    """

    def __init__(
        self,
        threshold: float = 0.60,
        max_regen: int = 3,
        min_duration_s: float = 2.0,
    ) -> None:
        self.threshold = threshold
        self.max_regen = max_regen
        self.min_duration_s = min_duration_s
        self._encoder = None

    def _get_encoder(self):
        """Lazy-load Resemblyzer's VoiceEncoder on first use."""
        if self._encoder is None:
            from resemblyzer import VoiceEncoder

            self._encoder = VoiceEncoder("cpu")
            logger.info("VoiceEncoder loaded on CPU")
        return self._encoder

    def build_reference_embeddings(
        self,
        voice_map: VoiceMap,
    ) -> dict[str, np.ndarray]:
        """Build reference speaker embeddings from voice map clips.

        For each character and narrator in voice_map, loads their reference
        clip and computes a 256-dim embedding.  Skips characters with
        placeholder clip paths.

        Args:
            voice_map: Complete voice map with clip paths.

        Returns:
            Dict mapping character/speaker name to 256-dim embedding.
        """
        from resemblyzer import preprocess_wav

        encoder = self._get_encoder()
        embeddings: dict[str, np.ndarray] = {}

        # Build list of (name, clip_path) to process
        entries: list[tuple[str, str]] = []
        entries.append(("narrator", voice_map.narrator.clip_path))
        for assignment in voice_map.characters:
            entries.append((assignment.character_name, assignment.clip_path))

        for name, clip_path in entries:
            if clip_path.startswith(_PLACEHOLDER_PREFIX):
                logger.debug("Skipping placeholder clip for '%s': %s", name, clip_path)
                continue

            path = Path(clip_path)
            if not path.exists():
                logger.warning(
                    "Reference clip not found for '%s': %s — skipping",
                    name, clip_path,
                )
                continue

            try:
                wav = preprocess_wav(path)
                embedding = encoder.embed_utterance(wav)
                embeddings[name] = embedding
                logger.debug(
                    "Built reference embedding for '%s' from %s", name, clip_path,
                )
            except Exception as exc:
                logger.warning(
                    "Failed to build embedding for '%s': %s", name, exc,
                )

        return embeddings

    def compute_segment_embedding(
        self,
        wav_path: Path,
    ) -> np.ndarray | None:
        """Compute speaker embedding for a synthesized segment.

        Returns None if segment is too short for reliable embeddings.

        Args:
            wav_path: Path to the segment WAV file.

        Returns:
            256-dim numpy embedding, or None if too short.
        """
        import soundfile as sf
        from resemblyzer import preprocess_wav

        if not wav_path.exists():
            logger.warning("Segment WAV not found: %s", wav_path)
            return None

        # Check duration
        info = sf.info(str(wav_path))
        if info.duration < self.min_duration_s:
            logger.debug(
                "Segment %s too short (%.2fs < %.2fs) — skipping",
                wav_path.name, info.duration, self.min_duration_s,
            )
            return None

        encoder = self._get_encoder()
        wav = preprocess_wav(wav_path)
        return encoder.embed_utterance(wav)

    @staticmethod
    def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        """Compute cosine similarity between two embedding vectors.

        Args:
            a: First embedding vector.
            b: Second embedding vector.

        Returns:
            Cosine similarity in [-1.0, 1.0] range.
        """
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))

    def check_segment(
        self,
        wav_path: Path,
        ref_embedding: np.ndarray,
    ) -> tuple[float, bool]:
        """Check a segment against its character's reference embedding.

        Returns (1.0, True) for too-short segments (skip check).

        Args:
            wav_path: Path to segment WAV.
            ref_embedding: Reference speaker embedding.

        Returns:
            Tuple of (similarity_score, passes_threshold).
        """
        seg_embedding = self.compute_segment_embedding(wav_path)
        if seg_embedding is None:
            # Too short or missing — pass by default
            return 1.0, True

        similarity = self.cosine_similarity(seg_embedding, ref_embedding)
        return similarity, similarity >= self.threshold

    def unload(self) -> None:
        """Delete the encoder to free memory."""
        if self._encoder is not None:
            del self._encoder
            self._encoder = None
            logger.info("VoiceEncoder unloaded")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def run_voice_consistency(
    book_dir: Path,
    voice_map: VoiceMap,
    attributed_segments: list[dict],
    threshold: float = 0.60,
    max_regen: int = 3,
    engine_config: SynthesisConfig | None = None,
    libritts_root: Path | None = None,
) -> ConsistencyReport:
    """Run voice consistency verification across all synthesized segments.

    Checks every segment's speaker embedding against its character's
    reference voice.  Optionally regenerates outliers using the TTS engine.

    Args:
        book_dir: Book output directory containing wavs/.
        voice_map: Complete voice map with reference clip paths.
        attributed_segments: List of segment metadata dicts.
        threshold: Cosine similarity threshold.
        max_regen: Maximum regeneration attempts per failing segment.
        engine_config: If provided, enables regeneration mode.
            If None, runs in verification-only mode.
        libritts_root: LibriTTS-R audio root for voice references.

    Returns:
        ConsistencyReport with check results.
    """
    verifier = VoiceConsistencyVerifier(
        threshold=threshold,
        max_regen=max_regen,
    )
    report = ConsistencyReport()

    # Build reference embeddings
    logger.info("Building reference speaker embeddings...")
    ref_embeddings = verifier.build_reference_embeddings(voice_map)
    logger.info("Built %d reference embeddings", len(ref_embeddings))

    if not ref_embeddings:
        logger.warning("No reference embeddings available — skipping verification")
        report.write_report(book_dir / "voice_consistency_report.json")
        verifier.unload()
        return report

    # Build speaker lookup: segment speaker -> reference name
    wavs_dir = book_dir / "wavs"

    for seg in attributed_segments:
        seg_id = seg.get("id", 0)
        ch_num = seg.get("chapter", 0)
        speaker = seg.get("speaker", "narrator")

        wav_path = wavs_dir / f"ch{ch_num:02d}" / f"seg_{seg_id:04d}.wav"

        if not wav_path.exists():
            report.add_skipped()
            continue

        # Find reference embedding for this speaker
        ref_embedding = ref_embeddings.get(speaker)
        if ref_embedding is None:
            # Try narrator fallback
            ref_embedding = ref_embeddings.get("narrator")
        if ref_embedding is None:
            report.add_skipped()
            continue

        # Check segment
        similarity, passed = verifier.check_segment(wav_path, ref_embedding)

        if passed or similarity == 1.0:
            # Passed or skipped (too short)
            if similarity == 1.0 and passed:
                report.add_skipped()
            else:
                report.add_result(seg_id, speaker, similarity, passed=True)
            continue

        # Below threshold
        if engine_config is not None:
            # Regeneration mode
            best_similarity = similarity
            best_wav_path = wav_path
            regenerated = False

            for attempt in range(1, max_regen + 1):
                logger.info(
                    "Regenerating seg %d (attempt %d/%d, sim=%.3f < %.3f)",
                    seg_id, attempt, max_regen, similarity, threshold,
                )
                try:
                    from src.synthesis.engine_factory import create_engine

                    engine = create_engine(engine_config)
                    engine.load_model()

                    # Find reference clip for this speaker
                    ref_clip = voice_map.narrator.clip_path
                    for a in voice_map.characters:
                        if a.character_name == speaker:
                            ref_clip = a.clip_path
                            break

                    result = engine.generate(
                        seg.get("text", ""),
                        ref_clip,
                        segment_type=seg.get("type", "narration"),
                    )
                    engine.save_wav_atomic(result, str(wav_path))
                    engine.unload()

                    # Re-check
                    new_sim, new_passed = verifier.check_segment(
                        wav_path, ref_embedding,
                    )

                    if new_sim > best_similarity:
                        best_similarity = new_sim

                    if new_passed:
                        report.add_result(
                            seg_id, speaker, new_sim,
                            passed=True, regenerated=True, attempt=attempt,
                        )
                        regenerated = True
                        break

                except Exception as exc:
                    logger.warning(
                        "Regeneration attempt %d for seg %d failed: %s",
                        attempt, seg_id, exc,
                    )

            if not regenerated:
                report.add_result(
                    seg_id, speaker, best_similarity, passed=False,
                )
                report.add_flagged(
                    seg_id, speaker, best_similarity, str(best_wav_path),
                )
        else:
            # Verification-only mode — just flag
            report.add_result(seg_id, speaker, similarity, passed=False)
            report.add_flagged(seg_id, speaker, similarity, str(wav_path))

    # Write report and clean up
    report.write_report(book_dir / "voice_consistency_report.json")
    verifier.unload()

    return report
