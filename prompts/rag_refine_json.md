# RAG Refine Prompt

You are refining an existing answer with additional context.

## Original Question
{query_str}

## Previous Answer (JSON)
{existing_answer}

## New Context
{context_str}

## Instructions

1. **Merge Information**: Combine the previous answer with any new relevant information from the new context.
2. **Preserve Valid JSON**: The output must remain valid JSON matching the schema.
3. **Update Citations**: Add new citations for information from the new context.
4. **No Contradictions**: If new context contradicts previous answer, prefer the more specific/recent information.
5. **Maintain Style**: Keep the same `answer_style` unless the new context significantly changes the nature of the answer.

## Output Format

Return the refined answer as valid JSON. No other text.
