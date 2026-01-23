"""
Structured Output Parsing and Validation.

Parses JSON outputs from the LLM and validates against expected schemas.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Citation:
    """A citation from the RAG response."""
    file_id: str
    file_name: str
    snippets: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "file_id": self.file_id,
            "file_name": self.file_name,
            "snippets": self.snippets,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "Citation":
        return cls(
            file_id=data.get("file_id", ""),
            file_name=data.get("file_name", ""),
            snippets=data.get("snippets", []),
        )


@dataclass
class StructuredResponse:
    """Structured response from the LLM."""
    answer: str
    refused: bool = False
    refusal_reason: str = "unknown"
    answer_style: str = "paragraph"
    entities: List[str] = field(default_factory=list)
    citations: List[Citation] = field(default_factory=list)
    parse_error: Optional[str] = None
    raw_text: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "answer": self.answer,
            "refused": self.refused,
            "refusal_reason": self.refusal_reason,
            "answer_style": self.answer_style,
            "entities": self.entities,
            "citations": [c.to_dict() for c in self.citations],
            "parse_error": self.parse_error,
        }

    @classmethod
    def from_dict(cls, data: Dict, raw_text: str = None) -> "StructuredResponse":
        citations = []
        for c in data.get("citations", []):
            if isinstance(c, dict):
                citations.append(Citation.from_dict(c))

        return cls(
            answer=data.get("answer", ""),
            refused=data.get("refused", False),
            refusal_reason=data.get("refusal_reason", "unknown"),
            answer_style=data.get("answer_style", "paragraph"),
            entities=data.get("entities", []),
            citations=citations,
            raw_text=raw_text,
        )

    @classmethod
    def refused_response(
        cls, reason: str = "unknown", error: str = None
    ) -> "StructuredResponse":
        """Create a refused response (used for parse failures)."""
        return cls(
            answer="I'm sorry, I couldn't process that request.",
            refused=True,
            refusal_reason=reason,
            parse_error=error,
        )

    def to_markdown(self) -> str:
        """Convert to markdown format for UI display."""
        if self.refused:
            return f"**Answer:** {self.answer}"

        lines = [f"**Answer:** {self.answer}"]

        if self.citations:
            lines.append("\n**Sources:**")
            for i, citation in enumerate(self.citations, 1):
                lines.append(f"- [{i}] {citation.file_name}")

        return "\n".join(lines)


# Valid enum values
VALID_REFUSAL_REASONS = {"not_in_docs", "out_of_scope", "unsafe", "unknown"}
VALID_ANSWER_STYLES = {"bullets", "sections", "paragraph"}


def _extract_json(text: str) -> Optional[str]:
    """
    Extract JSON from text that might contain markdown code fences.

    Args:
        text: Raw text possibly containing JSON

    Returns:
        Extracted JSON string or None
    """
    if not text:
        return None

    text = text.strip()

    # Try to find JSON in code fence
    code_fence_match = re.search(
        r"```(?:json)?\s*\n?(.*?)\n?```",
        text,
        re.DOTALL
    )
    if code_fence_match:
        return code_fence_match.group(1).strip()

    # Try to find JSON object directly
    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        return brace_match.group(0)

    return text


def _validate_rag_json(data: Dict) -> List[str]:
    """
    Validate RAG JSON against expected schema.

    Returns list of validation errors (empty if valid).
    """
    errors = []

    if "answer" not in data:
        errors.append("Missing required field: answer")

    if "refused" in data and not isinstance(data["refused"], bool):
        errors.append("Field 'refused' must be boolean")

    if "refusal_reason" in data:
        if data["refusal_reason"] not in VALID_REFUSAL_REASONS:
            errors.append(
                f"Invalid refusal_reason: {data['refusal_reason']}. "
                f"Valid values: {VALID_REFUSAL_REASONS}"
            )

    if "answer_style" in data:
        if data["answer_style"] not in VALID_ANSWER_STYLES:
            errors.append(
                f"Invalid answer_style: {data['answer_style']}. "
                f"Valid values: {VALID_ANSWER_STYLES}"
            )

    if "citations" in data:
        if not isinstance(data["citations"], list):
            errors.append("Field 'citations' must be a list")
        else:
            for i, citation in enumerate(data["citations"]):
                if not isinstance(citation, dict):
                    errors.append(f"Citation {i} must be an object")
                elif "file_id" not in citation and "file_name" not in citation:
                    errors.append(
                        f"Citation {i} must have file_id or file_name"
                    )

    return errors


def parse_rag_json(text: str) -> StructuredResponse:
    """
    Parse RAG JSON output from the LLM.

    Args:
        text: Raw LLM output

    Returns:
        StructuredResponse (with parse_error if parsing failed)
    """
    if not text:
        return StructuredResponse.refused_response(
            "unknown", "Empty response from LLM"
        )

    try:
        # Extract JSON from possible markdown wrapping
        json_str = _extract_json(text)
        if not json_str:
            return StructuredResponse.refused_response(
                "unknown", "Could not extract JSON from response"
            )

        # Parse JSON
        data = json.loads(json_str)

        # Validate
        errors = _validate_rag_json(data)
        if errors:
            logger.warning("RAG JSON validation errors: %s", errors)
            # Still try to use partially valid data

        response = StructuredResponse.from_dict(data, raw_text=text)
        if errors:
            response.parse_error = "; ".join(errors)

        return response

    except json.JSONDecodeError as e:
        logger.warning("Failed to parse RAG JSON: %s", e)
        logger.debug("Raw text: %s", text[:500])
        return StructuredResponse.refused_response(
            "unknown", f"JSON parse error: {e}"
        )
    except Exception as e:
        logger.error("Unexpected error parsing RAG JSON: %s", e)
        return StructuredResponse.refused_response(
            "unknown", f"Parse error: {e}"
        )


def parse_casual_json(text: str) -> StructuredResponse:
    """
    Parse casual chat JSON output from the LLM.

    Args:
        text: Raw LLM output

    Returns:
        StructuredResponse (with empty citations)
    """
    if not text:
        return StructuredResponse(
            answer="Hello! How can I help you?",
            refused=False,
            answer_style="paragraph",
            raw_text=text,
        )

    try:
        json_str = _extract_json(text)
        if not json_str:
            # For casual, just use the text as-is
            return StructuredResponse(
                answer=text,
                refused=False,
                answer_style="paragraph",
                raw_text=text,
            )

        data = json.loads(json_str)

        # Casual responses should have empty citations
        data["citations"] = []

        return StructuredResponse.from_dict(data, raw_text=text)

    except json.JSONDecodeError:
        # For casual, use raw text as answer
        return StructuredResponse(
            answer=text,
            refused=False,
            answer_style="paragraph",
            raw_text=text,
        )
    except Exception as e:
        logger.warning("Error parsing casual JSON: %s", e)
        return StructuredResponse(
            answer=text if text else "Hello!",
            refused=False,
            answer_style="paragraph",
            parse_error=str(e),
            raw_text=text,
        )
