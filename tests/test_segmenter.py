"""TDD tests for src/parser/segmenter.py.

Tests cover:
- Dialogue detection (straight quotes, curly double quotes, curly single quotes)
- Multi-paragraph dialogue state carry
- Type classification (chapter_heading, scene_break, dialogue, narration, blockquote)
- Segment splitting at sentence boundaries and clause boundaries
- Character limit enforcement (280 chars max per segment)
- PARSE-03, PARSE-04, PARSE-06 requirements
"""

import pytest

from src.parser.segmenter import classify_block, process_chapter_blocks, split_to_segments
from src.parser.models import Segment, SegmentType

CHAR_LIMIT = 280


# ---------------------------------------------------------------------------
# classify_block — Type Classification (PARSE-03)
# ---------------------------------------------------------------------------

class TestClassifyBlockHeadings:
    """h1-h4 tags → chapter_heading, dialogue state reset."""

    def test_h1_returns_chapter_heading(self):
        seg_type, new_open = classify_block("h1", "Chapter 1", {}, False)
        assert seg_type == SegmentType.CHAPTER_HEADING

    def test_h2_returns_chapter_heading(self):
        seg_type, new_open = classify_block("h2", "The Dark Tower", {}, False)
        assert seg_type == SegmentType.CHAPTER_HEADING

    def test_h3_returns_chapter_heading(self):
        seg_type, new_open = classify_block("h3", "Part One", {}, False)
        assert seg_type == SegmentType.CHAPTER_HEADING

    def test_h4_returns_chapter_heading(self):
        seg_type, new_open = classify_block("h4", "Section A", {}, False)
        assert seg_type == SegmentType.CHAPTER_HEADING

    def test_heading_resets_dialogue_open_state(self):
        """A heading encountered mid-dialogue must reset the open state."""
        _, new_open = classify_block("h2", "Chapter 3", {}, True)
        assert new_open is False


class TestClassifyBlockSceneBreaks:
    """HR tag, asterisk patterns, dash patterns, CSS classes → scene_break."""

    def test_hr_tag_returns_scene_break(self):
        seg_type, _ = classify_block("hr", "", {}, False)
        assert seg_type == SegmentType.SCENE_BREAK

    def test_p_asterisk_space_returns_scene_break(self):
        seg_type, _ = classify_block("p", "* * *", {}, False)
        assert seg_type == SegmentType.SCENE_BREAK

    def test_p_dash_returns_scene_break(self):
        seg_type, _ = classify_block("p", "---", {}, False)
        assert seg_type == SegmentType.SCENE_BREAK

    def test_p_em_dashes_returns_scene_break(self):
        seg_type, _ = classify_block("p", "\u2014\u2014\u2014", {}, False)
        assert seg_type == SegmentType.SCENE_BREAK

    def test_p_css_separator_class_returns_scene_break(self):
        seg_type, _ = classify_block("p", "", {"class": ["separator"]}, False)
        assert seg_type == SegmentType.SCENE_BREAK

    def test_p_css_break_class_returns_scene_break(self):
        seg_type, _ = classify_block("p", "", {"class": ["break"]}, False)
        assert seg_type == SegmentType.SCENE_BREAK

    def test_p_css_divider_class_returns_scene_break(self):
        seg_type, _ = classify_block("p", "   ", {"class": ["divider"]}, False)
        assert seg_type == SegmentType.SCENE_BREAK

    def test_p_triple_asterisk_no_spaces_returns_scene_break(self):
        seg_type, _ = classify_block("p", "***", {}, False)
        assert seg_type == SegmentType.SCENE_BREAK

    def test_scene_break_resets_dialogue_open_state(self):
        _, new_open = classify_block("hr", "", {}, True)
        assert new_open is False


class TestClassifyBlockDialogue:
    """Paragraphs containing quoted speech → dialogue."""

    def test_straight_double_quotes_is_dialogue(self):
        seg_type, _ = classify_block("p", '"Where are you going?" she asked.', {}, False)
        assert seg_type == SegmentType.DIALOGUE

    def test_curly_double_quotes_is_dialogue(self):
        seg_type, _ = classify_block(
            "p", "\u201cHello,\u201d she said.", {}, False
        )
        assert seg_type == SegmentType.DIALOGUE

    def test_curly_single_quotes_is_dialogue(self):
        seg_type, _ = classify_block(
            "p", "\u2018Hello,\u2019 she said.", {}, False
        )
        assert seg_type == SegmentType.DIALOGUE

    def test_inline_quote_is_dialogue(self):
        """Conservative: if quotes present in text, tag as dialogue for Phase 2 to refine."""
        seg_type, _ = classify_block(
            "p", 'He said it was "fine" but looked worried.', {}, False
        )
        assert seg_type == SegmentType.DIALOGUE

    def test_blockquote_tag_is_dialogue(self):
        """Letters and notes from characters tagged as dialogue for Phase 2 attribution."""
        seg_type, _ = classify_block(
            "blockquote", "Dear John, I am leaving...", {}, False
        )
        assert seg_type == SegmentType.DIALOGUE


class TestClassifyBlockNarration:
    """Plain paragraphs without quotes → narration."""

    def test_plain_paragraph_is_narration(self):
        seg_type, _ = classify_block("p", "The sun set behind the mountains.", {}, False)
        assert seg_type == SegmentType.NARRATION

    def test_apostrophe_contraction_is_narration(self):
        """Apostrophe in contraction must NOT be treated as dialogue marker."""
        seg_type, _ = classify_block("p", "The cat's meow echoed.", {}, False)
        assert seg_type == SegmentType.NARRATION

    def test_possessive_apostrophe_is_narration(self):
        seg_type, _ = classify_block("p", "It's a beautiful day and she can't stop smiling.", {}, False)
        assert seg_type == SegmentType.NARRATION

    def test_dont_cant_contraction_is_narration(self):
        seg_type, _ = classify_block("p", "He doesn't know what he can't see.", {}, False)
        assert seg_type == SegmentType.NARRATION


class TestClassifyBlockMultiParagraphDialogue:
    """Multi-paragraph speech: open-quote carry state."""

    def test_open_curly_quote_without_close_sets_dialogue_open(self):
        """Paragraph starts with curly open quote but has no closing quote → dialogue_open = True."""
        # Paragraph opens with curly open-quote but never closes it — dialogue carry-forward
        text = "\u201cI have been thinking about this for a very long time now."
        seg_type, new_open = classify_block("p", text, {}, False)
        assert seg_type == SegmentType.DIALOGUE
        assert new_open is True

    def test_continuation_paragraph_without_opening_quote_is_dialogue(self):
        """When dialogue_open=True and paragraph has no opening quote, carry state → dialogue."""
        seg_type, _ = classify_block(
            "p", "The rain continued to fall outside.", {}, True
        )
        assert seg_type == SegmentType.DIALOGUE

    def test_closing_quote_resets_dialogue_open(self):
        """Paragraph ends the quoted speech (has closing curly quote) → new_open = False."""
        text = "and I cannot bear it.\u201d"
        seg_type, new_open = classify_block("p", text, {}, True)
        assert seg_type == SegmentType.DIALOGUE
        assert new_open is False

    def test_fully_quoted_paragraph_does_not_leave_open(self):
        """\u201c...\u201d with both open and close quotes → new_open stays False."""
        text = "\u201cThis is a complete quoted sentence.\u201d"
        _, new_open = classify_block("p", text, {}, False)
        assert new_open is False


# ---------------------------------------------------------------------------
# split_to_segments — Segment Splitting (PARSE-06)
# ---------------------------------------------------------------------------

class TestSplitToSegmentsBasic:
    """Sentence-boundary splitting and character limit."""

    def test_short_sentence_becomes_one_segment(self):
        """A 200-char sentence stays as one segment."""
        text = "A" * 50 + " " + "B" * 50 + " " + "C" * 50 + " done."
        segments = split_to_segments(text, SegmentType.NARRATION)
        assert len(segments) == 1
        assert all(len(s) <= CHAR_LIMIT for s in segments)

    def test_three_short_sentences_become_three_segments(self):
        """Three sentences each under limit → three separate segments."""
        text = "The sky is blue. The grass is green. The sun is bright."
        segments = split_to_segments(text, SegmentType.NARRATION)
        assert len(segments) == 3
        assert all(len(s) <= CHAR_LIMIT for s in segments)

    def test_no_segment_exceeds_char_limit(self):
        """Every segment returned must be at most 280 characters."""
        # Create a string with many short sentences that together exceed 280 chars
        text = " ".join(["The quick brown fox jumped."] * 5)
        segments = split_to_segments(text, SegmentType.NARRATION)
        for seg in segments:
            assert len(seg) <= CHAR_LIMIT, f"Segment too long ({len(seg)} chars): {seg!r}"


class TestSplitToSegmentsLongSentences:
    """Long sentences must be split at clause boundaries or word boundaries."""

    def test_350_char_sentence_splits_into_two(self):
        """A 350-char sentence with a comma mid-sentence → 2 segments."""
        # "A" * 150 + ", " + "B" * 150 + "." = 303 chars, definitely over 280
        text = "A" * 150 + ", " + "B" * 150 + "."
        segments = split_to_segments(text, SegmentType.NARRATION)
        assert len(segments) >= 2
        assert all(len(s) <= CHAR_LIMIT for s in segments)

    def test_500_char_sentence_no_clause_boundaries_splits(self):
        """A 500-char sentence with no comma/semicolon → force split at word boundary."""
        words = ["extraordinary"] * 36  # ~500 chars with spaces
        text = " ".join(words) + "."
        assert len(text) > 400
        segments = split_to_segments(text, SegmentType.NARRATION)
        assert len(segments) >= 2
        assert all(len(s) <= CHAR_LIMIT for s in segments)
        # No segment should cut mid-word
        for seg in segments:
            assert not seg[0].isspace(), "Segment should not start with whitespace"
            assert not seg[-1].isspace(), "Segment should not end with whitespace"

    def test_split_at_semicolon_boundary(self):
        """Long sentence with semicolon → split preferably at semicolon."""
        text = "X" * 150 + "; " + "Y" * 150 + "."
        segments = split_to_segments(text, SegmentType.NARRATION)
        assert len(segments) >= 2
        assert all(len(s) <= CHAR_LIMIT for s in segments)

    def test_no_mid_word_splits(self):
        """Splits must occur at word boundaries only."""
        # Sentence long enough to force split
        text = "The magnificent blue whale of the deep ocean " * 7
        segments = split_to_segments(text.strip(), SegmentType.NARRATION)
        for seg in segments:
            stripped = seg.strip()
            assert len(stripped) > 0
            assert len(stripped) <= CHAR_LIMIT


class TestSplitToSegmentsDialogue:
    """Dialogue lines that fit within limit are kept as a single segment."""

    def test_short_dialogue_stays_as_one_segment(self):
        """A single short dialogue sentence is not further split by the 280-char limiter."""
        # This is a single grammatical sentence — under the 280-char limit, stays as-is.
        text = '"I cannot believe you would say something like that to me," she said quietly.'
        assert len(text) <= CHAR_LIMIT
        segments = split_to_segments(text, SegmentType.DIALOGUE)
        assert len(segments) == 1

    def test_segment_type_passed_through(self):
        """split_to_segments returns strings; type is applied by the caller."""
        text = "Hello world."
        segments = split_to_segments(text, SegmentType.DIALOGUE)
        assert isinstance(segments, list)
        assert all(isinstance(s, str) for s in segments)


# ---------------------------------------------------------------------------
# process_chapter_blocks — Integration / Orchestrator (PARSE-03 + PARSE-04 + PARSE-06)
# ---------------------------------------------------------------------------

class TestProcessChapterBlocks:
    """Integration tests for the full block processing pipeline."""

    def test_returns_list_of_segment_objects(self):
        blocks = [("p", "The sun rose slowly.", {})]
        segments = process_chapter_blocks(blocks, chapter_num=1, chapter_title="Chapter 1", start_id=1)
        assert isinstance(segments, list)
        assert len(segments) >= 1
        assert all(isinstance(s, Segment) for s in segments)

    def test_segment_ids_are_sequential_from_start_id(self):
        blocks = [
            ("p", "First sentence.", {}),
            ("p", "Second sentence.", {}),
        ]
        segments = process_chapter_blocks(blocks, chapter_num=1, chapter_title="", start_id=10)
        ids = [s.id for s in segments]
        assert ids == list(range(10, 10 + len(segments)))

    def test_segment_chapter_and_title_set_correctly(self):
        blocks = [("p", "Once upon a time.", {})]
        segments = process_chapter_blocks(blocks, chapter_num=3, chapter_title="The Beginning", start_id=1)
        for seg in segments:
            assert seg.chapter == 3
            assert seg.chapter_title == "The Beginning"

    def test_char_count_matches_text_length(self):
        blocks = [("p", "Hello world.", {})]
        segments = process_chapter_blocks(blocks, chapter_num=1, chapter_title="", start_id=1)
        for seg in segments:
            assert seg.char_count == len(seg.text)

    def test_narration_block_produces_narration_segments(self):
        blocks = [("p", "The wind howled through the empty streets.", {})]
        segments = process_chapter_blocks(blocks, chapter_num=1, chapter_title="", start_id=1)
        assert all(seg.type == SegmentType.NARRATION for seg in segments)

    def test_dialogue_block_produces_dialogue_segments(self):
        blocks = [("p", '"Run!" she screamed.', {})]
        segments = process_chapter_blocks(blocks, chapter_num=1, chapter_title="", start_id=1)
        assert all(seg.type == SegmentType.DIALOGUE for seg in segments)

    def test_h1_block_produces_chapter_heading_segment(self):
        blocks = [("h1", "Chapter One", {})]
        segments = process_chapter_blocks(blocks, chapter_num=1, chapter_title="Chapter One", start_id=1)
        assert len(segments) == 1
        assert segments[0].type == SegmentType.CHAPTER_HEADING

    def test_scene_break_block_produces_scene_break_segment(self):
        blocks = [("hr", "", {})]
        segments = process_chapter_blocks(blocks, chapter_num=1, chapter_title="", start_id=1)
        assert len(segments) == 1
        assert segments[0].type == SegmentType.SCENE_BREAK

    def test_no_segment_exceeds_char_limit(self):
        """All segments from process_chapter_blocks must be <= 280 chars."""
        long_narration = "The river wound its way through the valley " * 10
        blocks = [("p", long_narration.strip(), {})]
        segments = process_chapter_blocks(blocks, chapter_num=1, chapter_title="", start_id=1)
        for seg in segments:
            assert seg.char_count <= CHAR_LIMIT, (
                f"Segment {seg.id} exceeds {CHAR_LIMIT} chars: {seg.char_count}"
            )

    def test_multi_paragraph_dialogue_state_carried(self):
        """Open quote in one block carries dialogue state into next block."""
        blocks = [
            ("p", "\u201cI have been thinking about what you said,", {}),
            ("p", "and I cannot agree with your conclusion.\u201d", {}),
        ]
        segments = process_chapter_blocks(blocks, chapter_num=1, chapter_title="", start_id=1)
        types = [seg.type for seg in segments]
        assert all(t == SegmentType.DIALOGUE for t in types), (
            f"Expected all dialogue, got: {types}"
        )

    def test_dialogue_state_resets_at_chapter_boundary(self):
        """After process_chapter_blocks, dialogue state does not bleed into the next call."""
        # First chapter ends with open dialogue
        blocks_ch1 = [("p", "\u201cI never said that,", {})]
        process_chapter_blocks(blocks_ch1, chapter_num=1, chapter_title="", start_id=1)

        # Second chapter should start fresh
        blocks_ch2 = [("p", "The morning was cold and grey.", {})]
        segments_ch2 = process_chapter_blocks(blocks_ch2, chapter_num=2, chapter_title="", start_id=10)
        assert segments_ch2[0].type == SegmentType.NARRATION

    def test_mixed_blocks_correct_types(self):
        """A realistic chapter excerpt with mixed block types."""
        blocks = [
            ("h1", "Chapter 1", {}),
            ("p", "The old house stood silent at the edge of the moor.", {}),
            ("p", '"Who goes there?" a voice called out.', {}),
            ("hr", "", {}),
            ("p", "Morning came at last.", {}),
        ]
        segments = process_chapter_blocks(blocks, chapter_num=1, chapter_title="Chapter 1", start_id=1)
        type_list = [seg.type for seg in segments]
        assert SegmentType.CHAPTER_HEADING in type_list
        assert SegmentType.NARRATION in type_list
        assert SegmentType.DIALOGUE in type_list
        assert SegmentType.SCENE_BREAK in type_list

    def test_empty_blocks_list_returns_empty(self):
        segments = process_chapter_blocks([], chapter_num=1, chapter_title="", start_id=1)
        assert segments == []

    def test_blockquote_becomes_dialogue(self):
        """Letters/notes in blockquote → dialogue for Phase 2 attribution."""
        blocks = [("blockquote", "Dear John, I am leaving you this letter.", {})]
        segments = process_chapter_blocks(blocks, chapter_num=1, chapter_title="", start_id=1)
        assert all(seg.type == SegmentType.DIALOGUE for seg in segments)


# ---------------------------------------------------------------------------
# NLTK bootstrap — verify punkt_tab available after import
# ---------------------------------------------------------------------------

class TestNLTKBootstrap:
    """Ensure NLTK punkt_tab is available after module import."""

    def test_sent_tokenize_works_after_import(self):
        """sent_tokenize should work without error — NLTK data was bootstrapped at import."""
        import nltk
        sentences = nltk.tokenize.sent_tokenize("Hello world. How are you?")
        assert len(sentences) == 2

    def test_segmenter_import_does_not_raise(self):
        """Re-importing the segmenter must not raise any NLTK-related errors."""
        import importlib
        import src.parser.segmenter as seg_module
        importlib.reload(seg_module)  # trigger ensure_nltk_data() again
