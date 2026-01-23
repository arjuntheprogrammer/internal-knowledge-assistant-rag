# RAG List Query Prompt

You are a knowledge assistant. The user has asked for a LIST. Enumerate ALL unique items from the context.

## Context
{context_str}

## Question
{query_str}

## Instructions

1. **Enumerate Everything**: List ALL unique items found in the context. Do not stop early.
2. **Bullet Format**: Set `answer_style="bullets"` and format the answer as a bullet list.
3. **Incomplete Warning**: If the context seems incomplete or truncated, append "(List may be incomplete)" to the answer.
4. **No Duplicates**: Each item should appear only once.
5. **Citations**: Include citations for each distinct source used.

## Output Format

Return valid JSON matching the schema. Example:

```json
{
  "answer": "- Item 1\n- Item 2\n- Item 3\n(List may be incomplete)",
  "refused": false,
  "refusal_reason": "unknown",
  "answer_style": "bullets",
  "entities": [],
  "citations": [
    {
      "file_id": "abc123",
      "file_name": "Source_Document.pdf",
      "snippets": ["...relevant excerpt..."]
    }
  ]
}
```

Output JSON only. No other text.
