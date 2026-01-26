# Prompt Engineering Guide

This directory contains all LLM prompts used by the Internal Knowledge Assistant.

## Directory Structure

- `versions.json`: Simple mapping of prompt name to version string.
- `*.md`: The prompt template files.
- `examples/`: JSON files containing few-shot examples injected into prompts.

## How to Update a Prompt

1.  **Modify the Markdown File**: Edit the `.md` file (e.g., `rag_system.md`).
2.  **Increment Version**: Update the corresponding version in `versions.json`.
3.  **Validate Hashing**: The system uses whitespace-insensitive sha256 hashing. Small formatting changes will not trigger a new hash if the content remains the same.
4.  **Sync with Opik**: The system automatically registers new prompt versions/hashes in the Opik Prompt Library on first use.

## Use of Few-Shot Examples

Add a JSON file in `examples/` with the same name as the prompt (e.g., `rag.json`).
Structure:
```json
[
  {
    "user_query": "...",
    "llm_output": { ... }
  }
]
```

## Prompt Variable Substitution

The system supports standard LlamaIndex template variables:
- `{{SCHEMA}}`: Automatically injected JSON schema from Pydantic.
- `{{retrieval_context}}`: Grounding documents (for RAG).
- `{{user_query}}`: The incoming question.
