"""End-to-end voice matching orchestration.

Coordinates the full matching pipeline:
1. Check for cached voice_map.json
2. Load characters, segments, and speaker index
3. Classify cast (major/minor)
4. Build embedding index for fallback
5. Match narrator, major characters (LLM), minor characters (embedding)
6. Enforce uniqueness (dedup)
7. Select reference clips
8. Return VoiceMap for display and confirmation

The caller (pipeline.py) handles display, confirmation, and persistence.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from rich import print as rprint

from src.attribution.models import CharacterProfile
from src.matching.clip_selector import select_reference_clip
from src.matching.dedup import enforce_uniqueness
from src.matching.embedding_matcher import build_speaker_embeddings, match_character_embedding
from src.matching.models import CastClassification, VoiceMap, VoiceAssignment
from src.matching.speaker_index import classify_cast, filter_candidates, load_speaker_index
from src.matching.trait_matcher import match_character_llm, match_narrator_llm

logger = logging.getLogger(__name__)


def run_matching(
    book_dir: Path,
    libritts_data_dir: Path,
    libritts_audio_dir: Path | None = None,
) -> VoiceMap:
    """Run the full voice matching pipeline.

    Orchestrates speaker index loading, two-tier matching (LLM primary,
    embedding fallback), dedup enforcement, and reference clip selection.

    If voice_map.json already exists in book_dir, returns it immediately
    without re-running any matching (per VOICE-05 re-run caching).

    Args:
        book_dir: Book output directory containing characters.json and attributed.json.
        libritts_data_dir: Path to LibriTTS-P data directory (contains df1_en.csv).
        libritts_audio_dir: Path to LibriTTS-R audio directory (optional).

    Returns:
        VoiceMap with all assignments ready for display and confirmation.
    """
    voice_map_path = book_dir / "voice_map.json"

    # --- Step 1: Check for existing voice_map.json ---
    if voice_map_path.exists():
        rprint("[cyan]Using existing voice_map.json (delete to re-match)[/cyan]")
        with open(voice_map_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return VoiceMap.model_validate(data)

    # --- Step 2: Load inputs ---
    rprint("[bold cyan]Loading characters and segments...[/bold cyan]")

    characters_path = book_dir / "characters.json"
    attributed_path = book_dir / "attributed.json"

    with open(characters_path, "r", encoding="utf-8") as f:
        characters_data = json.load(f)
    characters = [CharacterProfile.model_validate(c) for c in characters_data]

    with open(attributed_path, "r", encoding="utf-8") as f:
        segments = json.load(f)

    rprint("[bold cyan]Loading speaker index...[/bold cyan]")
    speaker_index = load_speaker_index(libritts_data_dir)
    rprint(f"  Loaded [cyan]{len(speaker_index)}[/cyan] speakers from LibriTTS-P")

    # --- Step 3: Classify cast ---
    classification = classify_cast(characters_data, segments)
    rprint(
        f"\n[bold]Cast:[/bold] [cyan]{len(classification.major)}[/cyan] major, "
        f"[cyan]{len(classification.minor)}[/cyan] minor characters "
        f"(threshold: {classification.threshold} dialogue lines)"
    )
    rprint(f"  Narrator mode: [cyan]{classification.narrator_mode}[/cyan]")

    # --- Step 4: Build embedding index (for fallback) ---
    rprint("[bold cyan]Building speaker embeddings...[/bold cyan]")
    all_speakers = list(speaker_index.values())
    speaker_ids, speaker_embeddings = build_speaker_embeddings(all_speakers)
    rprint(f"  Encoded [cyan]{len(speaker_ids)}[/cyan] speakers into embedding space")

    # Track assigned speaker IDs to enforce uniqueness during matching
    assigned_ids: set[str] = set()
    all_assignments: list[VoiceAssignment] = []
    candidates_by_character: dict[str, list] = {}

    # --- Step 5: Match narrator first ---
    rprint("\n[bold cyan]Matching narrator...[/bold cyan]")
    # For narrator, use a broad pool — no strict gender filter
    narrator_candidates = filter_candidates(speaker_index, "unknown")
    narrator_assignment = match_narrator_llm(
        characters, segments, narrator_candidates,
        classification.narrator_mode, assigned_ids,
    )

    if narrator_assignment is None:
        # Embedding fallback for narrator
        rprint("  [yellow]LLM failed for narrator, using embedding fallback[/yellow]")
        # Create a simple narrator character profile for embedding matching
        from src.attribution.models import VoiceProfile
        narrator_char = CharacterProfile(
            name="narrator",
            aliases=[],
            gender="unknown",
            age_range="unknown",
            voice_profile=VoiceProfile(
                pitch="medium", pace="moderate", tone="neutral", accent="unknown",
                pace_style="measured", tone_style="clear", energy="moderate",
                typical_emotion="neutral", description="Neutral, clear narrator voice",
            ),
            personality_traits=["clear", "measured"],
            description="Book narrator",
            is_named=False,
        )
        narrator_assignment = match_character_embedding(
            narrator_char, speaker_ids, speaker_embeddings, assigned_ids
        )
        narrator_assignment = narrator_assignment.model_copy(
            update={"character_name": "narrator"}
        )

    assigned_ids.add(narrator_assignment.speaker_id)
    rprint(
        f"  Narrator -> speaker [cyan]{narrator_assignment.speaker_id}[/cyan] "
        f"({narrator_assignment.method}, confidence: {narrator_assignment.confidence:.2f})"
    )

    # --- Step 6: Match major characters (LLM primary) ---
    # Sort major characters by dialogue count (most dialogue first)
    dialogue_counts = {}
    for seg in segments:
        if seg.get("type") == "dialogue":
            speaker = seg.get("speaker", "")
            if speaker and speaker not in ("narrator", "unknown"):
                dialogue_counts[speaker] = dialogue_counts.get(speaker, 0) + 1

    major_chars = [
        c for c in characters if c.name in set(classification.major)
    ]
    major_chars.sort(key=lambda c: dialogue_counts.get(c.name, 0), reverse=True)

    if major_chars:
        rprint(f"\n[bold cyan]Matching {len(major_chars)} major characters (LLM)...[/bold cyan]")

    for char in major_chars:
        candidates = filter_candidates(speaker_index, char.gender, char.age_range)
        candidates_by_character[char.name] = candidates

        # If too many candidates, pre-rank with embeddings and take top 30
        filtered = [c for c in candidates if c.speaker_id not in assigned_ids]
        if len(filtered) > 50:
            # Use embedding to pre-rank, then send top 30 to LLM
            from sentence_transformers import util
            from src.matching.embedding_matcher import _get_model, _build_character_text

            model = _get_model()
            char_text = _build_character_text(char)
            char_emb = model.encode(char_text, convert_to_tensor=True, show_progress_bar=False)

            # Build embeddings for filtered candidates
            filtered_ids = [c.speaker_id for c in filtered]
            filtered_texts = [c.trait_text for c in filtered]
            filtered_embs = model.encode(filtered_texts, convert_to_tensor=True, show_progress_bar=False)

            scores = util.cos_sim(char_emb, filtered_embs)[0]
            scored = sorted(
                zip(filtered, [float(s) for s in scores]),
                key=lambda x: x[1],
                reverse=True,
            )
            candidates = [s[0] for s in scored[:30]]
        else:
            candidates = filtered

        assignment = match_character_llm(char, candidates, assigned_ids)

        if assignment is None:
            # Embedding fallback
            rprint(f"  [yellow]LLM failed for {char.name}, using embedding fallback[/yellow]")
            assignment = match_character_embedding(
                char, speaker_ids, speaker_embeddings, assigned_ids
            )

        assignment = assignment.model_copy(update={"is_major": True})
        assigned_ids.add(assignment.speaker_id)
        all_assignments.append(assignment)
        rprint(
            f"  {char.name} -> speaker [cyan]{assignment.speaker_id}[/cyan] "
            f"({assignment.method}, confidence: {assignment.confidence:.2f})"
        )

    # --- Step 7: Match minor characters (embedding preferred) ---
    minor_chars = [
        c for c in characters if c.name in set(classification.minor)
    ]
    minor_chars.sort(key=lambda c: dialogue_counts.get(c.name, 0), reverse=True)

    if minor_chars:
        rprint(f"\n[bold cyan]Matching {len(minor_chars)} minor characters (embedding)...[/bold cyan]")

    # For minor characters, only exclude major character speakers from assigned_ids
    major_assigned_ids = assigned_ids.copy()

    for char in minor_chars:
        candidates = filter_candidates(speaker_index, char.gender, char.age_range)
        candidates_by_character[char.name] = candidates

        assignment = match_character_embedding(
            char, speaker_ids, speaker_embeddings, major_assigned_ids
        )
        assignment = assignment.model_copy(update={"is_major": False})
        all_assignments.append(assignment)
        rprint(
            f"  {char.name} -> speaker [cyan]{assignment.speaker_id}[/cyan] "
            f"({assignment.method}, confidence: {assignment.confidence:.2f})"
        )

    # --- Step 8: Enforce uniqueness (dedup) ---
    rprint("\n[bold cyan]Enforcing voice uniqueness...[/bold cyan]")
    all_assignments = enforce_uniqueness(
        all_assignments, classification, segments,
        candidates_by_character, speaker_ids, speaker_embeddings,
    )

    # --- Step 9: Select reference clips ---
    if libritts_audio_dir is not None:
        rprint("[bold cyan]Selecting reference clips...[/bold cyan]")
        # Narrator clip
        narrator_clip = select_reference_clip(
            narrator_assignment.speaker_id, libritts_audio_dir
        )
        if narrator_clip:
            narrator_assignment = narrator_assignment.model_copy(
                update={"clip_path": narrator_clip}
            )
        else:
            narrator_assignment = narrator_assignment.model_copy(
                update={
                    "clip_path": "",
                    "warning": (narrator_assignment.warning or "")
                    + " No audio clip found."
                    if narrator_assignment.warning is None
                    else narrator_assignment.warning + " No audio clip found.",
                }
            )

        # Character clips
        for i, a in enumerate(all_assignments):
            clip = select_reference_clip(a.speaker_id, libritts_audio_dir)
            if clip:
                all_assignments[i] = a.model_copy(update={"clip_path": clip})
            else:
                all_assignments[i] = a.model_copy(
                    update={
                        "clip_path": "",
                        "warning": (
                            (a.warning + " No audio clip found.")
                            if a.warning
                            else "No audio clip found."
                        ),
                    }
                )
    else:
        # Placeholder paths when no audio directory provided
        narrator_assignment = narrator_assignment.model_copy(
            update={"clip_path": f"AUDIO_DIR/{narrator_assignment.speaker_id}/longest.wav"}
        )
        for i, a in enumerate(all_assignments):
            all_assignments[i] = a.model_copy(
                update={"clip_path": f"AUDIO_DIR/{a.speaker_id}/longest.wav"}
            )

    # --- Step 10: Build VoiceMap ---
    book_slug = book_dir.name

    voice_map = VoiceMap(
        book_slug=book_slug,
        narrator=narrator_assignment,
        characters=all_assignments,
        metadata={
            "created_at": datetime.now(timezone.utc).isoformat(),
            "total_speakers_evaluated": len(speaker_index),
            "major_characters": len(classification.major),
            "minor_characters": len(classification.minor),
            "narrator_mode": classification.narrator_mode,
            "libritts_audio_available": libritts_audio_dir is not None,
        },
    )

    return voice_map
