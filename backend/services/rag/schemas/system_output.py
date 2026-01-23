from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from .llm_output import LLMOutput


class RetrievalHit(BaseModel):
    file_id: str
    file_name: Optional[str] = None
    node_id: str
    score: Optional[float] = None
    text: Optional[str] = None


class SystemOutput(BaseModel):
    llm: LLMOutput
    retrieval: Dict[str, Any] = Field(
        default_factory=lambda: {
            "top_k": 0,
            "hits": [],
            "engine": "unknown",
            "citation_validation": {"invalid_count": 0, "reason": None}
        }
    )

    def to_markdown(self) -> str:
        """Helper to convert structured output back to markdown for UI."""
        # This allows RAGService.query to return a string by default
        return self.llm.answer_md
