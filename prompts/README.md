# Prompts Directory

This directory contains all LLM prompts used by the Internal Knowledge Assistant.

## Structure

| File | Purpose |
|------|---------|
| `versions.json` | Version strings for each prompt (for Opik tracking) |
| `shared_json_schema.md` | Common JSON schema and rules for all responses |
| `rag_default_json.md` | Default RAG query prompt |
| `rag_list_json.md` | List enumeration query prompt |
| `rag_refine_json.md` | Answer refinement prompt |
| `casual_json.md` | Casual chat/greeting prompt |

## Versioning

When you modify a prompt:
1. Update the prompt file
2. Increment the version in `versions.json`
3. The system will automatically track the new version in Opik

## JSON Output Format

All prompts enforce structured JSON output for deterministic evaluation:
- RAG responses include `answer`, `refused`, `citations`, etc.
- Casual responses use a simplified schema with no citations

## Adding New Prompts

1. Create a new `.md` file in this directory
2. Add an entry to `versions.json`
3. Register the prompt key in `backend/utils/prompt_loader.py` (add to `VALID_KEYS`)

## Code Integration

### PromptLoader

Prompts are loaded via `backend/utils/prompt_loader.py`:

```python
from backend.utils.prompt_loader import get_rag_prompt, get_casual_prompt, get_refine_prompt

# Get RAG prompt (automatically picks default or list based on query type)
prompt_spec = get_rag_prompt(is_list_query=False)

# Access prompt properties
print(prompt_spec.name)     # "shared_json_schema+rag_default_json"
print(prompt_spec.version)  # "1.0.0+1.0.0"
print(prompt_spec.hash)     # "abc123..."
print(prompt_spec.text)     # Full prompt text
```

### Opik Integration

Prompt metadata is automatically attached to traces:

```python
# Metadata format attached to traces
{
    "qa_prompt.name": "shared_json_schema+rag_default_json",
    "qa_prompt.version": "1.0.0+1.0.0",
    "qa_prompt.hash": "abc123...",
}
```

This allows:
- **Attribution**: Link any trace back to exact prompt version
- **Comparison**: Filter experiments by prompt version
- **Regression Detection**: Identify if prompt changes caused metric changes
