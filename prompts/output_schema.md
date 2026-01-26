# Output Schema Contract

You MUST output your response as a valid, strictly parseable JSON object.
Do NOT include any markdown code fences (like ```json), no backticks, and no text before or after the JSON.

## JSON Schema:

{{SCHEMA}}

## Critical Rules:
1. **Valid JSON**: The output must be perfectly parseable by a standard JSON parser.
2. **Strict Escaping**: You MUST escape all double quotes (`"`) and newlines (`\n`) within string values (especially in `answer_md` and `quote`). Use `\\"` for quotes and `\\n` for newlines if necessary to maintain valid JSON string boundaries.
3. **No Code Fences**: Do not wrap yours response in triple backticks. The first character must be `{` and the last character must be `}`.
4. **No Conversational Filler**: Do not provide and introduction, conclusion, or any text other than the JSON object.
5. **Node IDs**: For RAG, always use the `node_id` provided in the context metadata.
6. **Robustness**: Ensure that even if the content contains complex markdown (tables, lists), the JSON structure remains intact.
