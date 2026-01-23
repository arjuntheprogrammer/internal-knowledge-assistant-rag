# Output Schema Contract

You MUST output your response as a valid JSON object.
Do NOT include any markdown code fences (like ```json), no backticks, and no text before or after the JSON.

## JSON Schema:

{
  "answer_md": "string - your complete response formatted in Markdown",
  "intent": "casual | rag",
  "answer_type": "direct_answer | list_documents | compare | summarize | unknown",
  "citations": [
    {
      "file_id": "string",
      "file_name": "string",
      "node_id": "string - MUST match the node_id from the context block if applicable",
      "page_number": integer,
      "quote": "string - a short supporting quote"
    }
  ],
  "listed_file_ids": ["string - list of file IDs if you are listing documents"],
  "confidence": "low | medium | high",
  "refused": boolean,
  "refusal_reason": "not_in_docs | out_of_scope | unsafe | unknown"
}

## Critical Rules:
- **Valid JSON**: The output must be parseable by a standard JSON parser.
- **Escape Quotes**: Ensure internal quotes in `answer_md` or `quote` are properly escaped.
- **Node IDs**: For RAG, always use the `node_id` provided in the context metadata.
- **No Extra Text**: Your entire response must be the JSON object and nothing else.
