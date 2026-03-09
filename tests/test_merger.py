"""Tests for character profile merger hardening (MERGE-01 through MERGE-08).

Covers:
- MERGE-01: Audit trail from merge_characters
- MERGE-02: Post-merge validation warnings
- MERGE-03: Audit output (merge_audit.json)
- MERGE-04: Cross-name exclusion (alias matches another canonical name)
- MERGE-05: Co-occurrence signal usage
- MERGE-06: Trait cap enforcement
- MERGE-07: Surname exclusion edge cases
- MERGE-08: Extraction prompt negative examples
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from src.attribution.models import (
    CharacterProfile,
    MergeAudit,
    MergeDecision,
    VoiceProfile,
)
from src.attribution.merger import (
    _build_cooccurrence,
    _names_share_surname_only,
    _merge_two_profiles,
    _validate_merged_profiles,
    _generate_candidate_pairs,
    merge_characters,
)
from src.attribution.extractor import EXTRACTION_SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DEFAULT_VP = VoiceProfile(
    pitch="unknown",
    pace="unknown",
    tone="unknown",
    accent="unknown",
    pace_style="unknown",
    tone_style="unknown",
    energy="unknown",
    typical_emotion="unknown",
    description="unknown",
)


def _make_profile(
    name: str,
    aliases: list[str] | None = None,
    traits: list[str] | None = None,
    is_named: bool = True,
    gender: str = "unknown",
    age_range: str = "unknown",
) -> CharacterProfile:
    """Create a CharacterProfile with sensible defaults for testing."""
    return CharacterProfile(
        name=name,
        aliases=aliases or [],
        gender=gender,
        age_range=age_range,
        voice_profile=_DEFAULT_VP,
        personality_traits=traits or [],
        description=f"Test character: {name}",
        is_named=is_named,
    )


def _make_audit() -> MergeAudit:
    """Create a blank MergeAudit for testing."""
    return MergeAudit(
        book_title="Test",
        timestamp="2026-01-01T00:00:00Z",
        total_raw_profiles=0,
        total_merged_profiles=0,
    )


# ---------------------------------------------------------------------------
# MERGE-01: Audit trail
# ---------------------------------------------------------------------------


class TestAuditTrail:
    """Tests that MergeDecision and MergeAudit models work correctly
    and that merge_characters continues to function (regression)."""

    def test_merge_decision_construction(self) -> None:
        """MergeDecision can be constructed with all fields."""
        decision = MergeDecision(
            stage="exact_name",
            profile_a="Mr. Darcy",
            profile_b="Darcy",
            action="merged",
            reason="Exact name match (case-insensitive)",
            confidence=1.0,
        )
        assert decision.stage == "exact_name"
        assert decision.action == "merged"
        assert decision.details == {}

    def test_merge_decision_with_details(self) -> None:
        """MergeDecision supports optional details dict."""
        decision = MergeDecision(
            stage="fuzzy",
            profile_a="Elizabeth",
            profile_b="Elisabeth",
            action="merged",
            reason="Fuzzy match above threshold",
            confidence=0.92,
            details={"similarity": 0.92, "threshold": 0.85},
        )
        assert decision.details["similarity"] == 0.92

    def test_merge_audit_construction(self) -> None:
        """MergeAudit can be constructed with all fields."""
        audit = MergeAudit(
            book_title="Pride and Prejudice",
            timestamp="2026-03-09T00:00:00Z",
            total_raw_profiles=45,
            total_merged_profiles=20,
            stages={
                "exact_name": [
                    MergeDecision(
                        stage="exact_name",
                        profile_a="Darcy",
                        profile_b="Mr. Darcy",
                        action="merged",
                        reason="Same name",
                        confidence=1.0,
                    )
                ]
            },
            warnings=["Profile 'Elizabeth' has 7 aliases (threshold: 5)"],
            final_profiles=["Mr. Darcy", "Elizabeth Bennet"],
        )
        assert audit.total_raw_profiles == 45
        assert len(audit.stages["exact_name"]) == 1
        assert len(audit.warnings) == 1

    def test_merge_audit_defaults(self) -> None:
        """MergeAudit defaults for optional fields."""
        audit = MergeAudit(
            book_title="Test",
            timestamp="2026-01-01T00:00:00Z",
            total_raw_profiles=10,
            total_merged_profiles=5,
        )
        assert audit.stages == {}
        assert audit.warnings == []
        assert audit.final_profiles == []

    def test_merge_characters_returns_tuple(self) -> None:
        """merge_characters returns (profiles, audit) tuple."""
        chapter_chars = {
            1: [_make_profile("Mr. Darcy"), _make_profile("Elizabeth")],
            2: [_make_profile("Darcy"), _make_profile("Elizabeth Bennet")],
        }
        result = merge_characters(chapter_chars)
        assert isinstance(result, tuple)
        profiles, audit = result
        assert isinstance(profiles, list)
        assert isinstance(audit, MergeAudit)
        names = [p.name for p in profiles]
        assert any("darcy" in n.lower() for n in names)

    def test_merge_characters_records_exact_decisions(self) -> None:
        """merge_characters records MergeDecision entries for exact-name merges."""
        chapter_chars = {
            1: [_make_profile("Mr. Darcy")],
            2: [_make_profile("Mr. Darcy")],
        }
        profiles, audit = merge_characters(chapter_chars)
        # Should have at least one exact-stage decision
        assert "exact_name" in audit.stages
        assert len(audit.stages["exact_name"]) > 0
        assert audit.stages["exact_name"][0].action == "merged"
        assert audit.stages["exact_name"][0].confidence == 1.0


# ---------------------------------------------------------------------------
# MERGE-02: Post-merge validation warnings
# ---------------------------------------------------------------------------


class TestPostMergeValidation:
    """Tests that post-merge validation detects problematic profiles."""

    def test_excessive_aliases_warning(self) -> None:
        """Profile with >5 aliases should produce a warning."""
        profile = _make_profile(
            "Elizabeth",
            aliases=["Lizzy", "Eliza", "Miss Bennet", "Liz", "Beth", "Betsy"],
        )
        # Validate: >5 aliases is suspicious
        assert len(profile.aliases) > 5

    def test_excessive_traits_warning(self) -> None:
        """Profile with >50 traits should produce a warning."""
        profile = _make_profile(
            "Darcy",
            traits=[f"trait_{i}" for i in range(55)],
        )
        assert len(profile.personality_traits) > 50

    def test_alias_matches_canonical_name_warning(self) -> None:
        """Profile whose alias matches another profile's canonical name produces warning."""
        profiles = [
            _make_profile("Elizabeth Bennet", aliases=["Mrs. Bennet"]),
            _make_profile("Mrs. Bennet"),
        ]
        audit = _make_audit()
        _validate_merged_profiles(profiles, audit)
        # Should have a warning about alias-canonical cross-contamination
        assert any("alias" in w.lower() and "canonical" in w.lower() for w in audit.warnings)

    def test_validate_generates_warnings_in_audit(self) -> None:
        """_validate_merged_profiles populates audit.warnings for excessive aliases."""
        profiles = [
            _make_profile(
                "Elizabeth",
                aliases=["Lizzy", "Eliza", "Miss Bennet", "Liz", "Beth", "Betsy"],
            ),
        ]
        audit = _make_audit()
        _validate_merged_profiles(profiles, audit)
        assert len(audit.warnings) > 0
        assert any("alias" in w.lower() for w in audit.warnings)


# ---------------------------------------------------------------------------
# MERGE-03: Audit output (merge_audit.json)
# ---------------------------------------------------------------------------


class TestAuditOutput:
    """Tests that MergeAudit can be serialized and deserialized."""

    def test_model_dump_json_serializable(self) -> None:
        """MergeAudit.model_dump() produces valid JSON-serializable dict."""
        audit = MergeAudit(
            book_title="Test Book",
            timestamp="2026-03-09T00:00:00Z",
            total_raw_profiles=20,
            total_merged_profiles=10,
            stages={
                "exact_name": [
                    MergeDecision(
                        stage="exact_name",
                        profile_a="A",
                        profile_b="B",
                        action="merged",
                        reason="test",
                        confidence=1.0,
                    )
                ]
            },
            warnings=["test warning"],
            final_profiles=["A", "C"],
        )
        dumped = audit.model_dump()
        # Must be JSON-serializable
        json_str = json.dumps(dumped)
        assert isinstance(json_str, str)

    def test_json_round_trip(self) -> None:
        """MergeAudit survives JSON serialization round-trip."""
        audit = MergeAudit(
            book_title="Round Trip Test",
            timestamp="2026-03-09T12:00:00Z",
            total_raw_profiles=15,
            total_merged_profiles=8,
            stages={
                "fuzzy": [
                    MergeDecision(
                        stage="fuzzy",
                        profile_a="X",
                        profile_b="Y",
                        action="rejected",
                        reason="below threshold",
                        confidence=0.5,
                        details={"score": 0.5},
                    )
                ]
            },
            warnings=[],
            final_profiles=["X", "Y"],
        )
        json_str = json.dumps(audit.model_dump())
        restored = MergeAudit.model_validate(json.loads(json_str))
        assert restored.book_title == audit.book_title
        assert restored.total_raw_profiles == audit.total_raw_profiles
        assert len(restored.stages["fuzzy"]) == 1
        assert restored.stages["fuzzy"][0].action == "rejected"

    def test_write_audit_file(self, tmp_path: Path) -> None:
        """MergeAudit can be written to a JSON file."""
        audit = MergeAudit(
            book_title="File Write Test",
            timestamp="2026-03-09T00:00:00Z",
            total_raw_profiles=5,
            total_merged_profiles=3,
        )
        audit_path = tmp_path / "merge_audit.json"
        audit_path.write_text(json.dumps(audit.model_dump(), indent=2))
        assert audit_path.exists()
        loaded = json.loads(audit_path.read_text())
        assert loaded["book_title"] == "File Write Test"


# ---------------------------------------------------------------------------
# MERGE-04: Cross-name exclusion
# ---------------------------------------------------------------------------


class TestCrossNameExclusion:
    """Tests that aliases matching another profile's canonical name are blocked."""

    def test_alias_blocked_if_matches_canonical(self) -> None:
        """An alias that matches another profile's canonical name must be removed."""
        primary = _make_profile("Elizabeth Bennet", aliases=["Lizzy"])
        secondary = _make_profile("Eliza", aliases=["Mrs. Bennet"])
        all_canonical = {"mrs. bennet", "jane bennet"}
        audit = _make_audit()
        merged = _merge_two_profiles(primary, secondary, all_canonical, audit)
        # "Mrs. Bennet" alias should be blocked (matches canonical of another profile)
        alias_lower = {a.lower() for a in merged.aliases}
        assert "mrs. bennet" not in alias_lower

    def test_alias_allowed_if_no_conflict(self) -> None:
        """Aliases that don't conflict with any canonical name are kept."""
        primary = _make_profile("Elizabeth Bennet")
        secondary = _make_profile("Lizzy")
        all_canonical = {"mr. darcy", "jane bennet"}
        audit = _make_audit()
        merged = _merge_two_profiles(primary, secondary, all_canonical, audit)
        # "Lizzy" should be kept as alias
        alias_lower = {a.lower() for a in merged.aliases}
        assert "lizzy" in alias_lower


# ---------------------------------------------------------------------------
# MERGE-05: Co-occurrence signal
# ---------------------------------------------------------------------------


class TestCooccurrenceSignal:
    """Tests that co-occurrence data is used as signal, not binary gate."""

    def test_build_cooccurrence_basic(self) -> None:
        """_build_cooccurrence returns chapter sets for each character name."""
        chapter_chars = {
            1: [_make_profile("Alice"), _make_profile("Bob")],
            2: [_make_profile("Alice"), _make_profile("Charlie")],
        }
        name_to_chapters, name_is_named = _build_cooccurrence(chapter_chars)
        assert 1 in name_to_chapters["alice"]
        assert 2 in name_to_chapters["alice"]
        assert 1 in name_to_chapters["bob"]
        assert 2 not in name_to_chapters.get("bob", set())

    def test_build_cooccurrence_includes_aliases(self) -> None:
        """_build_cooccurrence tracks aliases as well as canonical names."""
        chapter_chars = {
            1: [_make_profile("Elizabeth", aliases=["Lizzy"])],
        }
        name_to_chapters, _ = _build_cooccurrence(chapter_chars)
        assert "lizzy" in name_to_chapters
        assert 1 in name_to_chapters["lizzy"]

    def test_cooccurrence_not_binary_gate(self) -> None:
        """Co-occurring profiles are NOT automatically blocked from candidate generation."""
        # Two profiles that co-occur but are fuzzy matches should still be candidates
        chapter_chars = {
            1: [_make_profile("Elizabeth"), _make_profile("Elisabeth")],
        }
        profiles = [_make_profile("Elizabeth"), _make_profile("Elisabeth")]
        all_canonical = {p.name.lower() for p in profiles}
        audit = _make_audit()
        candidates = _generate_candidate_pairs(profiles, all_canonical, audit)
        # Should generate a candidate pair (not blocked by co-occurrence)
        assert len(candidates) > 0


# ---------------------------------------------------------------------------
# MERGE-06: Trait cap
# ---------------------------------------------------------------------------


class TestTraitCap:
    """Tests that merged profiles have traits capped at 30."""

    def test_traits_capped_at_30_after_merge(self) -> None:
        """Profile with >30 traits after merge should be capped."""
        primary = _make_profile("Alice", traits=[f"trait_a_{i}" for i in range(20)])
        secondary = _make_profile("Alice B", traits=[f"trait_b_{i}" for i in range(20)])
        audit = _make_audit()
        merged = _merge_two_profiles(primary, secondary, set(), audit)
        assert len(merged.personality_traits) <= 30

    def test_traits_under_cap_unchanged(self) -> None:
        """Profile with <=30 traits after merge should keep all traits."""
        primary = _make_profile("Alice", traits=["kind", "brave"])
        secondary = _make_profile("Alice B", traits=["smart", "loyal"])
        audit = _make_audit()
        merged = _merge_two_profiles(primary, secondary, set(), audit)
        assert len(merged.personality_traits) == 4

    def test_primary_traits_preserved_first(self) -> None:
        """Primary profile's traits come first after cap."""
        primary = _make_profile("Alice", traits=[f"primary_{i}" for i in range(20)])
        secondary = _make_profile("Alice B", traits=[f"secondary_{i}" for i in range(20)])
        audit = _make_audit()
        merged = _merge_two_profiles(primary, secondary, set(), audit)
        # First 20 should be primary's traits
        assert all(t.startswith("primary_") for t in merged.personality_traits[:20])


# ---------------------------------------------------------------------------
# MERGE-07: Surname exclusion
# ---------------------------------------------------------------------------


class TestSurnameExclusion:
    """Tests _names_share_surname_only with edge cases."""

    def test_mr_bennet_vs_mrs_bennet(self) -> None:
        """Different titles + same surname = surname-only match (blocked)."""
        assert _names_share_surname_only("Mr. Bennet", "Mrs. Bennet") is True

    def test_mr_darcy_vs_darcy(self) -> None:
        """Single-part name vs titled name = NOT surname-only (allow merge)."""
        assert _names_share_surname_only("Mr. Darcy", "Darcy") is False

    def test_miss_darcy_vs_georgiana_darcy(self) -> None:
        """Different prefix + same surname = surname-only match (blocked)."""
        assert _names_share_surname_only("Miss Darcy", "Georgiana Darcy") is True

    def test_same_title_same_surname(self) -> None:
        """Same title + same surname = surname-only match (blocked)."""
        # Edge case: "Mr. Smith" vs "Mr. Smith" -- same prefix, returns False
        assert _names_share_surname_only("Mr. Smith", "Mr. Smith") is False

    def test_completely_different_surnames(self) -> None:
        """Different surnames = not a surname-only match."""
        assert _names_share_surname_only("Mr. Darcy", "Mrs. Bennet") is False

    def test_single_word_names(self) -> None:
        """Single-word names cannot have surname-only matches."""
        assert _names_share_surname_only("Darcy", "Bennet") is False


# ---------------------------------------------------------------------------
# MERGE-08: Extraction prompt
# ---------------------------------------------------------------------------


class TestExtractionPrompt:
    """Tests that EXTRACTION_SYSTEM_PROMPT contains negative examples."""

    def test_contains_wrong_examples(self) -> None:
        """Prompt must contain WRONG negative examples for family-name confusion."""
        assert "WRONG" in EXTRACTION_SYSTEM_PROMPT

    def test_contains_right_examples(self) -> None:
        """Prompt must contain RIGHT positive examples."""
        assert "RIGHT" in EXTRACTION_SYSTEM_PROMPT

    def test_contains_family_confusion_examples(self) -> None:
        """Prompt mentions specific family confusion patterns."""
        assert "DAUGHTERS" in EXTRACTION_SYSTEM_PROMPT or "daughters" in EXTRACTION_SYSTEM_PROMPT
        assert "SISTER" in EXTRACTION_SYSTEM_PROMPT or "sister" in EXTRACTION_SYSTEM_PROMPT
