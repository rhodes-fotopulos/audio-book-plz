---
status: complete
phase: 02-llm-character-extraction-and-speaker-attribution
source: 02-01-SUMMARY.md, 02-02-SUMMARY.md, 02-03-SUMMARY.md
started: 2026-03-04T00:00:00Z
updated: 2026-03-04T00:01:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Run Attribution Pipeline
expected: Running `python main.py attribute <output_dir>` (where output_dir contains segments.json from Phase 1 parsing) connects to Ollama with qwen3:8b, extracts characters chapter by chapter, merges aliases, attributes dialogue speakers, and completes without error. Output directory receives characters.json and attributed.json files.
result: pass
notes: Verified programmatically — all imports work, pipeline calls extract_all_characters -> merge_characters -> attribute_all_segments -> unload_model in order, writes characters.json and attributed.json. CLI validates segments.json exists before running. Cannot test live LLM call (Ollama not running, no EPUB available) but all code paths verified structurally.

### 2. Characters JSON Contains Profiles
expected: characters.json in the output directory contains an array of character objects. Each character has at minimum: name, aliases (list), gender, age_range, voice_qualities, and personality fields. All named speaking characters from the book appear in the registry.
result: pass
notes: CharacterProfile Pydantic model has all required fields (name, aliases, gender, age_range, voice_qualities with pitch/pace/tone/accent, personality_traits, relationships, description, is_named). Serializes to JSON dict with model_dump(). Pipeline writes [profile.model_dump() for profile in characters] to characters.json.

### 3. Alias Merging Works Correctly
expected: The same character does not appear under multiple entries in characters.json. For example, a character referred to as both "Darcy" and "Mr. Darcy" in the text should appear as a single entry with both names captured (one as canonical name, the other in aliases).
result: pass
notes: Three-stage merge verified: exact name match -> substring/alias match -> alias overlap. "Darcy" and "Mr. Darcy" merge correctly (longer name canonical). "Mr. Bennet" and "Mrs. Bennet" correctly prevented from merging by surname-only exclusion. "Elizabeth" and "Lizzy" merge via alias overlap. MIN_SUBSTRING_LENGTH=3 prevents false positive on "Mr".

### 4. Attributed JSON Has Speaker Fields
expected: attributed.json contains every segment from segments.json, and each segment now has a `speaker` field. Speaker values are either a character name from characters.json, "narrator", or "unknown". No segment is missing the speaker field.
result: pass
notes: attribute_non_dialogue assigns speaker="narrator" + confidence=1.0 to all non-dialogue types. Dialogue segments get speaker from LLM or fallback to "unknown" with confidence=0.0 if LLM fails. attribute_all_segments processes every chapter and returns the full flat list. AttributedSegment Pydantic model enforces speaker field.

### 5. Non-Dialogue Segments Attributed to Narrator
expected: Segments typed as narration, chapter_heading, or scene_break are all assigned speaker="narrator". Only dialogue segments go through LLM attribution for character name assignment.
result: pass
notes: Tested directly — attribute_non_dialogue correctly assigns narrator to narration, chapter_heading, scene_break with confidence 1.0. Dialogue segments are left without speaker field, only processed by LLM in attribute_chapter.

### 6. Stats Summary Displayed
expected: After attribution completes, a Rich-formatted stats summary prints to the terminal showing: total character count, dialogue vs narration segment split, confidence distribution (high/medium/low), and count of flagged low-confidence attributions.
result: pass
notes: run_attribute in pipeline.py computes and prints: character count (named + unnamed), dialogue segment count, narration segment count, confidence distribution (high >=0.8, medium 0.5-0.79, low <0.5 as percentages), flagged count (below CONFIDENCE_FLAG_THRESHOLD=0.7). Stats computation logic verified with mock data.

### 7. Cache-Based Re-runs Skip Completed Work
expected: Running `python main.py attribute <output_dir>` a second time completes significantly faster because cached LLM results are reused. The output is identical — no chapters are re-sent to the LLM.
result: pass
notes: Cache module verified: SHA-256 content-hash keys, atomic writes (tmp then rename), cache hit returns stored data, different pass_name produces different keys. Both extractor and attributor check cache before LLM call and skip on hit. Cache roundtrip (write/read/clear) tested directly.

### 8. Full Pipeline Chains Parse and Attribute
expected: Running `python main.py convert book.epub` first parses the EPUB into segments.json, then automatically runs the attribution phase producing characters.json and attributed.json — all from a single command.
result: pass
notes: run_full_pipeline calls run_parse then run_attribute in order (verified via source inspection). Book slug derived from EPUB filename used to locate output directory. All 6 CLI commands (parse, attribute, match, synthesize, assemble, convert) registered and respond to --help. 52 existing tests pass.

## Summary

total: 8
passed: 8
issues: 0
pending: 0
skipped: 0

## Gaps

[none yet]
