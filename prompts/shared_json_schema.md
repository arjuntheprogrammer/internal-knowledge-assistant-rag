# JSON Output Schema

You MUST output valid JSON only. No markdown, no backticks, no extra text before or after the JSON.

## RAG Response Schema

```json
{
  "answer": "string - the complete answer to the user's question",
  "refused": false,
  "refusal_reason": "not_in_docs | out_of_scope | unsafe | unknown",
  "answer_style": "bullets | sections | paragraph",
  "entities": ["list of entity names mentioned in the answer"],
  "citations": [
    {
      "file_id": "string - the file_id from the source document",
      "file_name": "string - the filename of the source",
      "snippets": ["short excerpts from the source that support the answer"]
    }
  ]
}
```

## Casual Response Schema

```json
{
  "answer": "string - brief friendly response",
  "refused": false,
  "refusal_reason": "unknown",
  "answer_style": "paragraph",
  "entities": [],
  "citations": []
}
```

## Rules

1. **JSON Only**: Output MUST be valid JSON. No markdown formatting, no code fences.
2. **All Keys Required**: Always include every key in the schema.
3. **Grounding**: For RAG responses, use ONLY information from the provided context.
4. **No Hallucination**: Never invent sources or cite documents not in the context.
5. **Refusal**: If the answer cannot be found in context, set `refused=true` with appropriate `refusal_reason`.
6. **Citations**: Each citation must reference a real `file_id` from source documents.

## Allowed Enum Values

- `refusal_reason`: `"not_in_docs"`, `"out_of_scope"`, `"unsafe"`, `"unknown"`
- `answer_style`: `"bullets"`, `"sections"`, `"paragraph"`
