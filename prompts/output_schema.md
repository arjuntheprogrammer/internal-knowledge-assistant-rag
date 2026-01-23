# Output Schema Contract

You MUST output your response as a valid JSON object.
Do NOT include any markdown code fences (like ```json), no backticks, and no text before or after the JSON.

## JSON Schema:


{{SCHEMA}}


## Critical Rules:
- **Valid JSON**: The output must be parseable by a standard JSON parser.
- **Escape Quotes**: Ensure internal quotes in `answer_md` or `quote` are properly escaped.
- **Node IDs**: For RAG, always use the `node_id` provided in the context metadata.
- **No Extra Text**: Your entire response must be the JSON object and nothing else.
