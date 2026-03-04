# Phase 2: LLM Character Extraction and Speaker Attribution - Research

**Researched:** 2026-03-03
**Domain:** Local LLM structured output, fiction dialogue attribution, chapter-level caching
**Confidence:** HIGH

## Summary

Phase 2 uses Qwen3 8B via Ollama to extract character profiles from novel text and attribute every dialogue line to a speaker. The `ollama` Python library (v0.6.1) provides native structured output support through Pydantic `model_json_schema()` passed to the `format` parameter, which constrains the model to produce valid JSON matching the schema. Qwen3 8B supports a 32,768-token native context window, which is sufficient for processing chapters in chunks with surrounding context for speaker identification.

The architecture follows a two-pass approach: (1) a character extraction pass that accumulates profiles across all chapters, merging aliases as they are discovered, and (2) an attribution pass that assigns a speaker to every dialogue and narration segment using the character registry as context. Both passes use chapter-level caching keyed by content hash so re-runs skip completed work.

**Primary recommendation:** Use the `ollama` Python library directly with Pydantic schemas for structured output, process chapters sequentially with explicit `num_ctx=32768`, disable thinking mode via `/no_think` in prompts for faster structured responses, and cache results per-chapter using content-hash-keyed JSON files.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **Character profile depth:** Rich descriptions: gender, age range, vocal qualities (pitch, pace, tone), personality traits, and accent if mentioned in text. Infer traits from context when reasonable. Single snapshot per character. Include character relationships.
- **Unknown speaker policy:** Always assign a best-guess speaker with a confidence score — never leave a line unattributed. Narrator reads ALL internal monologue and thought passages — only spoken-aloud dialogue gets character voices. Infer turn-taking in rapid untagged back-and-forth dialogue using conversation flow and context.
- **Minor character handling:** No threshold — every named character gets a full profile regardless of line count. Unnamed speakers get generic profiles with placeholder identities and inferred traits. Aggressively merge unnamed references that likely refer to the same person. Group dialogue attributed to narrator.
- **User review touchpoints:** No mandatory pause — pipeline continues automatically. Stats overview printed after completion. JSON output is human-readable (pretty-printed with indentation). Re-runs overwrite previous results.

### Claude's Discretion

- Confidence score threshold for flagging low-confidence attributions
- LLM prompting strategy and context window management
- Chapter caching implementation for incremental re-runs
- Alias detection heuristics

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| ATTR-01 | Extract character profiles (name, aliases, gender, age, voice qualities, personality) from novel text via local LLM | Ollama + Qwen3 8B structured output with Pydantic CharacterProfile schema; /no_think mode for speed |
| ATTR-02 | Character profiles accumulate across chapters, merging duplicates and aliases | Two-phase approach: extract per-chapter, then merge pass comparing names/aliases using string similarity and LLM confirmation |
| ATTR-03 | Each dialogue line attributed to a specific character or "unknown" via local LLM | Attribution pass sends segment batches with character registry + surrounding context; schema enforces speaker field |
| ATTR-04 | Narration segments attributed to "narrator" | Code-level rule: any segment with type "narration" gets speaker="narrator" without LLM call |
| ATTR-05 | LLM processes chapters in chunks that fit within context window (explicit num_ctx=32768) | Ollama options.num_ctx=32768; chunk sizing calculated from prompt template + chapter content + response budget |
| ATTR-06 | Attribution results cached per chapter so re-runs skip completed work | Content-hash-keyed JSON cache files in output directory; hashlib.sha256 of chapter text determines cache key |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| ollama | >=0.6.1 | Python client for Ollama REST API | Official Ollama Python library; native structured output via `format` parameter with Pydantic schemas |
| pydantic | >=2.0 | Schema definition and JSON validation | Ollama structured output requires `model_json_schema()`; validates LLM responses with `model_validate_json()` |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| hashlib | stdlib | Content hashing for cache keys | Generate SHA-256 of chapter text to detect content changes and key the cache |
| rich | >=13.0 (already installed) | Progress display and stats output | Show attribution progress per chapter, final stats summary |
| typer | >=0.24 (already installed) | CLI integration | Phase 2 `attribute` command already stubbed |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| ollama (direct) | langchain-ollama | Adds unnecessary abstraction layer; direct ollama is simpler for single-model single-task use |
| ollama (direct) | instructor + ollama | Extra dependency for retry/validation we can handle with simple try/except + Pydantic |
| pydantic schemas | raw JSON schema dicts | Pydantic provides validation on response side too, not just schema generation |
| JSON file cache | shelve / sqlite | JSON files are human-readable (user requirement), inspectable, and trivially debuggable |

**Installation:**
```bash
uv pip install ollama pydantic
```

## Architecture Patterns

### Recommended Project Structure
```
src/
├── parser/              # Phase 1 (existing)
├── attribution/         # Phase 2 (new)
│   ├── __init__.py      # Public API exports
│   ├── models.py        # Pydantic models for LLM schemas + output types
│   ├── llm_client.py    # Ollama wrapper: chat(), structured output, retry logic
│   ├── extractor.py     # Character extraction pass (chapters -> profiles)
│   ├── merger.py        # Alias detection and profile merging
│   ├── attributor.py    # Speaker attribution pass (segments + registry -> attributed)
│   └── cache.py         # Content-hash-keyed chapter cache
└── pipeline.py          # Updated: run_attribute() orchestrates Phase 2
```

### Pattern 1: Structured Output via Pydantic + Ollama
**What:** Define response schema as Pydantic model, pass `model_json_schema()` to Ollama's `format` parameter, validate response with `model_validate_json()`.
**When to use:** Every LLM call in this phase.
**Example:**
```python
# Source: https://docs.ollama.com/capabilities/structured-outputs
from ollama import chat
from pydantic import BaseModel

class CharacterProfile(BaseModel):
    name: str
    aliases: list[str]
    gender: str
    age_range: str
    voice_qualities: dict  # pitch, pace, tone, accent
    personality_traits: list[str]
    relationships: list[dict]  # {character: str, relation: str}
    confidence: float

class ExtractionResult(BaseModel):
    characters: list[CharacterProfile]

response = chat(
    model="qwen3:8b",
    messages=[
        {"role": "system", "content": "Extract characters from this chapter. /no_think"},
        {"role": "user", "content": chapter_text}
    ],
    format=ExtractionResult.model_json_schema(),
    options={"temperature": 0, "num_ctx": 32768}
)
result = ExtractionResult.model_validate_json(response.message.content)
```

### Pattern 2: Two-Pass Processing (Extract then Attribute)
**What:** First pass extracts characters from all chapters and builds a merged registry. Second pass attributes every segment using the registry as context.
**When to use:** This is the core processing pipeline for Phase 2.
**Why two passes:**
1. The attribution pass needs the full character registry to identify speakers — you can't attribute without knowing who exists
2. Character names/aliases may not appear until later chapters, so extraction must complete before attribution
3. Separation makes caching simpler — character cache and attribution cache are independent

### Pattern 3: Chapter Chunking with Context Windows
**What:** Process chapters individually with explicit `num_ctx=32768`. Calculate available tokens by subtracting prompt template overhead and response budget from context window.
**When to use:** Every chapter-level LLM call.
**Budget calculation:**
```python
CONTEXT_WINDOW = 32768
SYSTEM_PROMPT_TOKENS = 500    # system message + schema instruction
RESPONSE_BUDGET = 4096        # max tokens for structured response
REGISTRY_BUDGET = 2000        # character registry context (for attribution pass)
AVAILABLE_FOR_CONTENT = CONTEXT_WINDOW - SYSTEM_PROMPT_TOKENS - RESPONSE_BUDGET - REGISTRY_BUDGET
# ~26,172 tokens available for chapter text (attribution pass)
# ~28,172 tokens available for chapter text (extraction pass, no registry)
```
For chapters exceeding the budget, split at scene breaks or paragraph boundaries and process in sub-chunks, carrying context forward.

### Pattern 4: Content-Hash Cache
**What:** Hash chapter text with SHA-256, store results in `{output_dir}/.cache/{hash}.json`. Before processing, check if cache file exists — if so, skip LLM call.
**When to use:** Every chapter processing call (both extraction and attribution).
**Example:**
```python
import hashlib, json
from pathlib import Path

def get_cache_key(chapter_text: str, pass_name: str) -> str:
    content = f"{pass_name}:{chapter_text}"
    return hashlib.sha256(content.encode()).hexdigest()

def check_cache(cache_dir: Path, key: str):
    cache_file = cache_dir / f"{key}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text())
    return None

def write_cache(cache_dir: Path, key: str, data: dict):
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{key}.json"
    cache_file.write_text(json.dumps(data, indent=2, ensure_ascii=False))
```

### Anti-Patterns to Avoid
- **Sending entire book at once:** Exceeds 32K context window. Process chapter by chapter.
- **Parallel LLM requests:** Ollama on 16GB M4 can only serve one model instance efficiently. Sequential processing is the correct approach for this hardware.
- **Greedy decoding with Qwen3:** The Qwen3 model card explicitly warns against greedy decoding — causes repetition loops and degraded output. Always use temperature > 0 (recommended: 0.7 for non-thinking mode, but 0 is acceptable when `format` constrains output via structured schema).
- **Thinking mode for structured output:** Qwen3's thinking mode adds `<think>` blocks that waste tokens and slow down structured JSON generation. Use `/no_think` in system prompt.
- **Re-reading segments.json for each chapter:** Load once, group by chapter, process sequentially.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JSON schema generation | Manual dict schemas | Pydantic `model_json_schema()` | Type-safe, auto-validates responses, catches schema drift |
| JSON response validation | Manual json.loads + key checks | Pydantic `model_validate_json()` | Handles nested types, optional fields, defaults; raises clear errors |
| LLM structured output | Custom regex parsing of freeform text | Ollama `format` parameter | Grammar-constrained decoding at the token level — guaranteed valid JSON |
| Token counting | Character-based estimation | Rough 1:4 char-to-token ratio for English | Exact tokenization requires loading the model's tokenizer; 1:4 ratio is conservative and sufficient for budget calculations |

**Key insight:** Ollama's `format` parameter uses grammar-constrained decoding — it prevents the model from generating tokens that would produce invalid JSON. This is fundamentally more reliable than post-hoc parsing of freeform text. Pydantic adds a second validation layer on top.

## Common Pitfalls

### Pitfall 1: Ollama Default Context Window is 2048
**What goes wrong:** Model silently truncates input, losing early chapter content. Attribution fails because the model never sees the dialogue lines at the start of the chapter.
**Why it happens:** Ollama defaults to `num_ctx=2048` unless explicitly overridden.
**How to avoid:** Always pass `options={"num_ctx": 32768}` in every `ollama.chat()` call.
**Warning signs:** Suspiciously low character counts, missing characters from early chapters, nonsensical attributions.

### Pitfall 2: Qwen3 Thinking Mode Interferes with Structured Output
**What goes wrong:** Model generates `<think>...</think>` blocks before the JSON, consuming context window tokens and sometimes breaking the structured output parser.
**Why it happens:** Qwen3 defaults to thinking mode enabled.
**How to avoid:** Add `/no_think` to the system prompt or first user message. This makes Qwen3 behave like a standard non-thinking LLM and output JSON directly.
**Warning signs:** Slow response times, `<think>` appearing in output, JSON parse failures.

### Pitfall 3: Character Alias Fragmentation
**What goes wrong:** "Mr. Darcy", "Darcy", "Fitzwilliam", and "Mr. Fitzwilliam Darcy" appear as four separate characters in the registry.
**Why it happens:** Each chapter extraction produces independent character lists; naive string matching misses alias relationships.
**How to avoid:** After all chapters are extracted, run a merge pass that: (1) groups by exact name match, (2) checks substring containment (e.g., "Darcy" in "Mr. Darcy"), (3) uses the LLM to confirm ambiguous merges with context. Store canonical name + all aliases.
**Warning signs:** Character count much higher than expected for the novel, many single-appearance characters.

### Pitfall 4: Untagged Dialogue Turn-Taking Breaks
**What goes wrong:** In rapid back-and-forth dialogue without "said X" tags, the LLM loses track of who is speaking and assigns the wrong character.
**Why it happens:** Without explicit attribution cues, the model must infer from conversation flow, which is error-prone without sufficient context.
**How to avoid:** Include surrounding context (previous N segments) in the attribution prompt. Provide the character registry with relationship info so the model knows who is likely conversing. Set a lower confidence score for these inferences.
**Warning signs:** Alternating speakers suddenly assigned to the same character, confidence scores dropping in dialogue-heavy passages.

### Pitfall 5: Memory Pressure on 16GB M4
**What goes wrong:** Qwen3 8B at 32K context consumes significant memory. If Ollama is left running with the model loaded after Phase 2 completes, Phase 4 (Chatterbox TTS) cannot load.
**How to avoid:** After Phase 2 completes, explicitly unload the model by sending a request with `keep_alive=0`. The pipeline orchestrator should handle this at the phase boundary.
**Warning signs:** Phase 4 OOM errors, system swap usage spikes.

### Pitfall 6: Empty or Malformed LLM Responses
**What goes wrong:** Occasionally the LLM returns empty JSON, incomplete responses, or valid JSON that doesn't match the schema despite `format` parameter.
**Why it happens:** Edge cases in grammar-constrained decoding, context overflow, or model confusion with very short/unusual text.
**How to avoid:** Wrap every LLM call in retry logic (max 3 attempts). Validate with Pydantic `model_validate_json()`. Log failures for debugging. On persistent failure, return a fallback result with low confidence.
**Warning signs:** `ValidationError` exceptions, empty `characters` lists for chapters that clearly have dialogue.

## Code Examples

### Complete LLM Client Pattern
```python
# Source: https://docs.ollama.com/capabilities/structured-outputs
from ollama import chat
from pydantic import BaseModel, ValidationError
import logging

logger = logging.getLogger(__name__)

MAX_RETRIES = 3

def call_llm_structured(
    system_prompt: str,
    user_content: str,
    schema_class: type[BaseModel],
    num_ctx: int = 32768,
) -> BaseModel | None:
    """Call Ollama with structured output and retry logic."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = chat(
                model="qwen3:8b",
                messages=[
                    {"role": "system", "content": f"{system_prompt} /no_think"},
                    {"role": "user", "content": user_content},
                ],
                format=schema_class.model_json_schema(),
                options={
                    "temperature": 0,
                    "num_ctx": num_ctx,
                    "num_predict": 4096,
                },
            )
            result = schema_class.model_validate_json(response.message.content)
            return result
        except ValidationError as e:
            logger.warning(f"Attempt {attempt}: validation error: {e}")
        except Exception as e:
            logger.warning(f"Attempt {attempt}: LLM error: {e}")

    logger.error(f"All {MAX_RETRIES} attempts failed")
    return None
```

### Model Unloading After Phase Completion
```python
# Source: https://docs.ollama.com/faq
from ollama import chat

def unload_model(model: str = "qwen3:8b") -> None:
    """Explicitly unload model from Ollama to free memory."""
    chat(
        model=model,
        messages=[],
        keep_alive=0,
    )
```

### Narration Attribution (No LLM Needed)
```python
# ATTR-04: Narration segments attributed to "narrator"
def attribute_non_dialogue(segments: list[dict]) -> list[dict]:
    """Attribute narration, headings, and scene breaks without LLM."""
    for seg in segments:
        if seg["type"] in ("narration", "chapter_heading", "scene_break"):
            seg["speaker"] = "narrator"
            seg["confidence"] = 1.0
    return segments
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| BookNLP + spaCy coreference | LLM-based extraction with structured output | 2024-2025 | Eliminates complex NLP pipeline; single model handles extraction + attribution |
| Custom JSON parsing of freeform LLM text | Ollama grammar-constrained decoding (`format` param) | Ollama v0.5.0 (2024) | Guaranteed valid JSON; no regex/parsing code needed |
| Temperature=0 (greedy) for determinism | Temperature=0 with `format` constraint | Qwen3 (2025) | Qwen3 warns against greedy without schema; `format` provides determinism at token level |
| Generic LLMs | Qwen3 thinking/non-thinking hybrid | 2025 | `/no_think` mode gives fast structured output; thinking mode available for complex disambiguation if needed |

**Deprecated/outdated:**
- BookNLP: Still useful for academic NLP but overkill when you have a capable LLM with structured output
- NeuralCoref / spaCy coreference: Legacy approaches; LLM handles this better for fiction dialogue
- Manual JSON schema dicts with Ollama: Pydantic `model_json_schema()` is the standard pattern now

## Open Questions

1. **Exact token budget per chapter**
   - What we know: Qwen3 8B has 32K native context. English text averages ~4 chars per token.
   - What's unclear: Exact overhead of system prompt + schema instruction + response in tokens (varies by prompt length).
   - Recommendation: Use conservative 1:4 char-to-token ratio. Log actual `prompt_eval_count` from Ollama response to calibrate after first run. Warn if chapter exceeds budget.

2. **Merge accuracy for complex alias chains**
   - What we know: Substring matching handles "Darcy" / "Mr. Darcy". LLM can confirm ambiguous cases.
   - What's unclear: How well Qwen3 8B handles edge cases like nicknames ("Lizzy" for "Elizabeth Bennet") without explicit textual evidence.
   - Recommendation: First pass uses heuristics (substring, shared surname). Second pass uses LLM confirmation for remaining candidates. Log merge decisions for debugging.

3. **Confidence threshold for flagging**
   - What we know: User wants best-guess attribution always, plus confidence scores.
   - What's unclear: What threshold meaningfully separates "probably right" from "might be wrong" for this model.
   - Recommendation: Start with 0.7 as flag threshold. Print count of low-confidence attributions in final stats. Adjust based on real-world testing.

## Sources

### Primary (HIGH confidence)
- [Ollama Structured Outputs Documentation](https://docs.ollama.com/capabilities/structured-outputs) — Pydantic schema format, Python examples, temperature settings
- [Ollama API Reference](https://github.com/ollama/ollama/blob/main/docs/api.md) — Chat endpoint, options parameters (num_ctx, num_predict, keep_alive, temperature)
- [Qwen3-8B Model Card (Hugging Face)](https://huggingface.co/Qwen/Qwen3-8B) — 32K native context, recommended parameters, thinking/non-thinking modes, anti-greedy warning
- [Ollama Python Package (PyPI)](https://pypi.org/project/ollama/) — v0.6.1, Python >=3.8, MIT license

### Secondary (MEDIUM confidence)
- [SIG: Speaker Identification via Prompt-Based Generation (ACL 2024)](https://arxiv.org/html/2312.14590v1) — Context window strategy: surrounding 1024 tokens for speaker identification
- [Ollama Blog: Structured Outputs](https://ollama.com/blog/structured-outputs) — format parameter usage patterns, multi-model support
- [Ollama FAQ: Model Unloading](https://docs.ollama.com/faq) — keep_alive=0 for explicit unload
- [Qwen3 + Structured Output Guide](https://www.glukhov.org/post/2025/09/llm-structured-output-with-ollama-in-python-and-go/) — Practical implementation with Pydantic

### Tertiary (LOW confidence)
- [BookNLP](https://github.com/booknlp/booknlp) — Academic baseline for character extraction; confirms the problem domain but we use LLM instead

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — Ollama + Pydantic structured output is well-documented with official examples
- Architecture: HIGH — Two-pass extract/attribute is the standard approach for this problem; chapter-level processing matches context window constraints
- Pitfalls: HIGH — Context window defaults, thinking mode interference, and memory pressure are well-documented issues with clear mitigations

**Research date:** 2026-03-03
**Valid until:** 2026-04-03 (30 days — Ollama/Qwen3 ecosystem is stable)
