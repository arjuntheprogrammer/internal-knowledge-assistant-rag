import json
import logging
import re
from typing import Optional, Type, TypeVar
from pydantic import BaseModel, ValidationError

from .schemas.llm_output import LLMOutput

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


def _extract_json_block(text: str) -> str:
    """Extracts JSON from text, handling markdown blocks if present."""
    if not text:
        return ""

    text = text.strip()

    # Try to find JSON in code fence
    code_fence_match = re.search(
        r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if code_fence_match:
        return code_fence_match.group(1).strip()

    # Try to find JSON object directly
    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        return brace_match.group(0)

    return text


def parse_structured_output(text: str, model_class: Type[T]) -> T:
    """Parses text into a Pydantic model with robust JSON extraction."""
    json_str = _extract_json_block(text)

    try:
        data = json.loads(json_str)
        return model_class.model_validate(data)
    except (json.JSONDecodeError, ValidationError) as e:
        logger.warning("Failed to parse LLM output: %s", e)
        raise e


def repair_llm_json(llm, bad_text: str, model_class: Type[T]) -> T:
    """Attempt a single repair of malformed JSON."""
    from backend.utils.prompt_loader import load_prompt

    repair_prompt = f"""
    The following text was intended to be valid JSON matching the schema, but it failed to parse.
    Please fix the JSON and return ONLY the corrected JSON object.

    Schema description:
    {load_prompt("output_schema.md")}

    Malformed Text:
    {bad_text}

    Corrected JSON:
    """

    try:
        repaired_text = llm.complete(repair_prompt).text
        return parse_structured_output(repaired_text, model_class)
    except Exception as e:
        logger.error("JSON repair attempt failed: %s", e)
        raise e


def get_safe_llm_output(intent: str, refusal_reason: str = "unknown", error: Optional[Exception] = None) -> LLMOutput:
    """Returns a safe fallback LLMOutput with helpful error suggestions."""
    msg = "I'm sorry, I encountered an error processing the response. Please try again."

    if error:
        if "validation error" in str(error).lower():
            msg = "I'm sorry, the model's response didn't match the expected format. [Suggestion: Try rephrasing your question or check the prompt version.]"
        elif "json" in str(error).lower():
            msg = "I'm sorry, I couldn't understand the model's response. [Suggestion: Avoid using special characters that might break JSON.]"

    return LLMOutput(
        answer_md=msg,
        intent=intent,  # type: ignore
        answer_type="unknown",
        refused=True,
        refusal_reason=refusal_reason  # type: ignore
    )
