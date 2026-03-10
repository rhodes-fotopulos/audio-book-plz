"""Tests for character name disambiguation pass (DISAMB-01 through DISAMB-10).

Covers:
- DISAMB-01: Consistent profiles → no changes
- DISAMB-02: Gender divergence → group flagged
- DISAMB-03: Age divergence → group flagged
- DISAMB-04: Known-ambiguous title+surname pattern → flagged
- DISAMB-05: Split application rewrites names + adds aliases
- DISAMB-06: Name-change link adds correct aliases
- DISAMB-07: Audit trail complete and JSON-serializable
- DISAMB-08: Context builder stays within token budget
- DISAMB-09: Cache hit skips LLM call
- DISAMB-10: Single-profile groups skipped
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from src.attribution.models import (
    CharacterProfile,
    DisambiguatedIdentity,
    DisambiguationAudit,
    DisambiguationDecision,
    DisambiguationResult,
    NameChangeLink,
    VoiceProfile,
)
from src.attribution.disambiguator import (
    _apply_disambiguations,
    _apply_name_changes,
    _build_chapter_segments_map,
    _build_disambiguation_context,
    _description_jaccard,
    _extract_dialogue_snippets,
    _find_ambiguous_groups,
    disambiguate_characters,
    MAX_CONTEXT_TOKENS,
)


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
    description: str | None = None,
) -> CharacterProfile:
    """Create a CharacterProfile with sensible defaults for testing."""
    return CharacterProfile(
        name=name,
        aliases=aliases or [],
        gender=gender,
        age_range=age_range,
        voice_profile=_DEFAULT_VP,
        personality_traits=traits or [],
        description=description or f"Test character: {name}",
        is_named=is_named,
    )


def _make_audit() -> DisambiguationAudit:
    """Create a blank DisambiguationAudit for testing."""
    return DisambiguationAudit(
        total_names_analyzed=0,
        ambiguous_groups_found=0,
        splits_applied=0,
        name_changes_found=0,
    )


def _make_segments(chapter: int, texts: list[tuple[str, str]]) -> list[dict]:
    """Create segments for a chapter. texts is list of (type, text) tuples."""
    return [
        {"chapter": chapter, "type": t, "text": txt, "id": i}
        for i, (t, txt) in enumerate(texts)
    ]


# ---------------------------------------------------------------------------
# DISAMB-01: Consistent profiles → no changes
# ---------------------------------------------------------------------------


class TestConsistentProfiles:
    """Consistent profiles with identical attributes should not be flagged."""

    def test_no_ambiguity_when_profiles_consistent(self):
        chapter_characters = {
            1: [_make_profile("Mr. Darcy", gender="male", age_range="young adult")],
            2: [_make_profile("Mr. Darcy", gender="male", age_range="young adult")],
        }
        groups = _find_ambiguous_groups(chapter_characters)
        assert len(groups) == 0

    def test_full_pass_no_changes(self):
        chapter_characters = {
            1: [_make_profile("Mr. Darcy", gender="male")],
            2: [_make_profile("Mr. Darcy", gender="male")],
        }
        segments = _make_segments(1, [("narration", "Darcy spoke.")]) + \
                   _make_segments(2, [("narration", "Darcy left.")])

        # Mock LLM to return no changes (should not even be called)
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)

            # No ambiguous groups → LLM never called
            with patch("src.attribution.disambiguator.call_llm_structured") as mock_llm:
                # name-change detection will be called once
                mock_llm.return_value = DisambiguationResult(
                    identities=[], name_changes=[]
                )
                result_chars, audit = disambiguate_characters(
                    chapter_characters, segments, cache_dir
                )

            assert audit.splits_applied == 0
            assert audit.ambiguous_groups_found == 0
            # Profiles unchanged
            assert result_chars[1][0].name == "Mr. Darcy"
            assert result_chars[2][0].name == "Mr. Darcy"


# ---------------------------------------------------------------------------
# DISAMB-02: Gender divergence → group flagged
# ---------------------------------------------------------------------------


class TestGenderDivergence:
    """Profiles with conflicting genders should be flagged as ambiguous."""

    def test_gender_conflict_flags_group(self):
        chapter_characters = {
            1: [_make_profile("Taylor", gender="female")],
            2: [_make_profile("Taylor", gender="male")],
        }
        groups = _find_ambiguous_groups(chapter_characters)
        assert "taylor" in groups
        assert len(groups["taylor"]) == 2

    def test_unknown_gender_no_conflict(self):
        chapter_characters = {
            1: [_make_profile("Taylor", gender="female")],
            2: [_make_profile("Taylor", gender="unknown")],
        }
        groups = _find_ambiguous_groups(chapter_characters)
        assert "taylor" not in groups


# ---------------------------------------------------------------------------
# DISAMB-03: Age divergence → group flagged
# ---------------------------------------------------------------------------


class TestAgeDivergence:
    """Profiles with conflicting age ranges should be flagged."""

    def test_age_conflict_flags_group(self):
        chapter_characters = {
            1: [_make_profile("Smith", age_range="young adult")],
            2: [_make_profile("Smith", age_range="elderly")],
        }
        groups = _find_ambiguous_groups(chapter_characters)
        assert "smith" in groups

    def test_unknown_age_no_conflict(self):
        chapter_characters = {
            1: [_make_profile("Smith", age_range="young adult")],
            2: [_make_profile("Smith", age_range="unknown")],
        }
        groups = _find_ambiguous_groups(chapter_characters)
        assert "smith" not in groups


# ---------------------------------------------------------------------------
# DISAMB-04: Known-ambiguous title+surname pattern → flagged
# ---------------------------------------------------------------------------


class TestKnownAmbiguousPattern:
    """Title+surname with other same-surname profiles should be flagged."""

    def test_miss_bennet_with_other_bennets(self):
        chapter_characters = {
            1: [
                _make_profile("Miss Bennet", gender="female"),
                _make_profile("Jane Bennet", gender="female"),
            ],
            2: [
                _make_profile("Miss Bennet", gender="female"),
                _make_profile("Mrs. Bennet", gender="female"),
            ],
        }
        groups = _find_ambiguous_groups(chapter_characters)
        assert "miss bennet" in groups

    def test_title_surname_without_others_not_flagged(self):
        """Title+surname alone (no other same-surname) → not ambiguous."""
        chapter_characters = {
            1: [_make_profile("Miss Darcy", gender="female")],
            2: [_make_profile("Miss Darcy", gender="female")],
        }
        groups = _find_ambiguous_groups(chapter_characters)
        assert "miss darcy" not in groups


# ---------------------------------------------------------------------------
# DISAMB-05: Split application rewrites names + adds aliases
# ---------------------------------------------------------------------------


class TestSplitApplication:
    """Split results should rewrite profile names and add original as alias."""

    def test_split_rewrites_name(self):
        chapter_characters = {
            1: [_make_profile("Miss Bennet")],
            3: [_make_profile("Miss Bennet")],
        }
        audit = _make_audit()
        result = DisambiguationResult(
            identities=[
                DisambiguatedIdentity(
                    resolved_name="Jane Bennet",
                    original_name="Miss Bennet",
                    chapter_numbers=[1],
                    reasoning="Context shows this is Jane",
                ),
                DisambiguatedIdentity(
                    resolved_name="Elizabeth Bennet",
                    original_name="Miss Bennet",
                    chapter_numbers=[3],
                    reasoning="Context shows this is Elizabeth",
                ),
            ],
            name_changes=[],
        )
        _apply_disambiguations(chapter_characters, result, audit)

        assert chapter_characters[1][0].name == "Jane Bennet"
        assert "Miss Bennet" in chapter_characters[1][0].aliases
        assert chapter_characters[3][0].name == "Elizabeth Bennet"
        assert "Miss Bennet" in chapter_characters[3][0].aliases
        assert audit.splits_applied == 2

    def test_no_split_when_names_match(self):
        """If resolved_name == original_name, no split applied."""
        chapter_characters = {
            1: [_make_profile("Miss Bennet")],
        }
        audit = _make_audit()
        result = DisambiguationResult(
            identities=[
                DisambiguatedIdentity(
                    resolved_name="Miss Bennet",
                    original_name="Miss Bennet",
                    chapter_numbers=[1],
                    reasoning="Same name",
                ),
            ],
            name_changes=[],
        )
        _apply_disambiguations(chapter_characters, result, audit)
        assert chapter_characters[1][0].name == "Miss Bennet"
        assert audit.splits_applied == 0


# ---------------------------------------------------------------------------
# DISAMB-06: Name-change link adds correct aliases
# ---------------------------------------------------------------------------


class TestNameChangeLinks:
    """Name-change links should add bidirectional aliases."""

    def test_name_change_adds_aliases(self):
        chapter_characters = {
            1: [_make_profile("Elizabeth Bennet")],
            50: [_make_profile("Mrs. Darcy")],
        }
        audit = _make_audit()
        changes = [
            NameChangeLink(
                earlier_name="Elizabeth Bennet",
                later_name="Mrs. Darcy",
                transition_chapter=45,
                reasoning="Marriage to Mr. Darcy",
            ),
        ]
        _apply_name_changes(chapter_characters, changes, audit)

        # Later name gets earlier name as alias
        assert "Elizabeth Bennet" in chapter_characters[50][0].aliases
        # Earlier name gets later name as alias
        assert "Mrs. Darcy" in chapter_characters[1][0].aliases
        assert audit.name_changes_found == 1


# ---------------------------------------------------------------------------
# DISAMB-07: Audit trail complete and JSON-serializable
# ---------------------------------------------------------------------------


class TestAuditTrail:
    """Audit trail should be complete and JSON-serializable."""

    def test_audit_json_serializable(self):
        audit = DisambiguationAudit(
            total_names_analyzed=10,
            ambiguous_groups_found=2,
            splits_applied=3,
            name_changes_found=1,
            decisions=[
                DisambiguationDecision(
                    original_name="Miss Bennet",
                    action="split",
                    details="Split into Jane and Elizabeth",
                    confidence=0.85,
                ),
            ],
            warnings=["Some warning"],
        )
        json_str = json.dumps(audit.model_dump())
        parsed = json.loads(json_str)
        assert parsed["total_names_analyzed"] == 10
        assert len(parsed["decisions"]) == 1
        assert parsed["decisions"][0]["action"] == "split"

    def test_audit_records_all_decisions(self):
        chapter_characters = {
            1: [_make_profile("Miss Bennet", gender="female")],
            2: [_make_profile("Miss Bennet", gender="female")],
        }
        # Add another Bennet to trigger ambiguous pattern
        chapter_characters[1].append(
            _make_profile("Jane Bennet", gender="female")
        )
        segments = _make_segments(1, [("narration", "Miss Bennet spoke.")]) + \
                   _make_segments(2, [("narration", "Miss Bennet arrived.")])

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)
            with patch("src.attribution.disambiguator.call_llm_structured") as mock_llm:
                mock_llm.return_value = DisambiguationResult(
                    identities=[], name_changes=[]
                )
                _, audit = disambiguate_characters(
                    chapter_characters, segments, cache_dir
                )

            assert audit.total_names_analyzed > 0
            assert len(audit.decisions) > 0


# ---------------------------------------------------------------------------
# DISAMB-08: Context builder stays within token budget
# ---------------------------------------------------------------------------


class TestContextBudget:
    """Context builder should not exceed token budget."""

    def test_context_within_budget(self):
        # Create many chapters with profiles
        chapter_characters: dict[int, list[CharacterProfile]] = {}
        for i in range(100):
            chapter_characters[i] = [
                _make_profile(
                    "Test Character",
                    description="A very detailed description " * 20,
                    traits=[f"trait_{j}" for j in range(10)],
                )
            ]

        entries = []
        for ch, profiles in chapter_characters.items():
            for p in profiles:
                entries.append((ch, p))

        chapter_segments_map = {i: [] for i in range(100)}
        context = _build_disambiguation_context(
            "test character", entries, chapter_segments_map
        )

        from src.attribution.llm_client import estimate_tokens
        tokens = estimate_tokens(context)
        assert tokens <= MAX_CONTEXT_TOKENS


# ---------------------------------------------------------------------------
# DISAMB-09: Cache hit skips LLM call
# ---------------------------------------------------------------------------


class TestCacheHit:
    """Cache hits should skip LLM calls on second run."""

    def test_cache_hit_skips_llm(self):
        chapter_characters = {
            1: [_make_profile("Taylor", gender="female")],
            2: [_make_profile("Taylor", gender="male")],
        }
        segments = _make_segments(1, [("narration", "Taylor spoke.")]) + \
                   _make_segments(2, [("narration", "Taylor arrived.")])

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)

            mock_result = DisambiguationResult(
                identities=[], name_changes=[]
            )

            with patch("src.attribution.disambiguator.call_llm_structured") as mock_llm:
                mock_llm.return_value = mock_result

                # First run — LLM called
                disambiguate_characters(chapter_characters, segments, cache_dir)
                first_call_count = mock_llm.call_count

                # Second run — should use cache
                # Reset characters since they may have been modified
                chapter_characters = {
                    1: [_make_profile("Taylor", gender="female")],
                    2: [_make_profile("Taylor", gender="male")],
                }
                disambiguate_characters(chapter_characters, segments, cache_dir)
                second_call_count = mock_llm.call_count

            # Second run should have fewer LLM calls (cache hits)
            assert second_call_count <= first_call_count


# ---------------------------------------------------------------------------
# DISAMB-10: Single-profile groups skipped
# ---------------------------------------------------------------------------


class TestSingleProfileGroups:
    """Names appearing in only one chapter should not be flagged."""

    def test_single_appearance_not_flagged(self):
        chapter_characters = {
            1: [_make_profile("Unique Character", gender="female")],
        }
        groups = _find_ambiguous_groups(chapter_characters)
        assert len(groups) == 0

    def test_single_with_many_others(self):
        """Single-profile names skipped even when other names are ambiguous."""
        chapter_characters = {
            1: [
                _make_profile("Unique", gender="female"),
                _make_profile("Ambig", gender="female"),
            ],
            2: [
                _make_profile("Ambig", gender="male"),
            ],
        }
        groups = _find_ambiguous_groups(chapter_characters)
        assert "unique" not in groups
        assert "ambig" in groups


# ---------------------------------------------------------------------------
# Additional helper tests
# ---------------------------------------------------------------------------


class TestHelpers:
    """Tests for helper functions."""

    def test_build_chapter_segments_map(self):
        segments = [
            {"chapter": 1, "type": "narration", "text": "Hello"},
            {"chapter": 1, "type": "dialogue", "text": "Hi"},
            {"chapter": 2, "type": "narration", "text": "World"},
        ]
        result = _build_chapter_segments_map(segments)
        assert len(result[1]) == 2
        assert len(result[2]) == 1

    def test_extract_dialogue_snippets(self):
        segs = [
            {"type": "narration", "text": "Mr. Darcy walked in."},
            {"type": "dialogue", "text": "Good morning."},
            {"type": "narration", "text": "He turned to leave."},
        ]
        snippets = _extract_dialogue_snippets("Mr. Darcy", segs)
        assert len(snippets) == 1
        assert snippets[0] == "Good morning."

    def test_extract_dialogue_snippets_no_match(self):
        segs = [
            {"type": "narration", "text": "The sun rose."},
            {"type": "dialogue", "text": "Good morning."},
        ]
        snippets = _extract_dialogue_snippets("Mr. Darcy", segs)
        assert len(snippets) == 0

    def test_description_jaccard_identical(self):
        assert _description_jaccard("hello world", "hello world") == 1.0

    def test_description_jaccard_disjoint(self):
        assert _description_jaccard("hello world", "foo bar") == 0.0

    def test_description_jaccard_partial(self):
        score = _description_jaccard("hello world foo", "hello world bar")
        assert 0.3 < score < 0.7

    def test_description_jaccard_empty(self):
        assert _description_jaccard("", "hello") == 0.0
        assert _description_jaccard("hello", "") == 0.0
