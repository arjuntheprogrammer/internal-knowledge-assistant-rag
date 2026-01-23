from typing import Any, Dict, List, Literal, Optional, Annotated
from pydantic import BaseModel, Field, BeforeValidator


def empty_str_to_none(v: Any) -> Any:
    if v == "":
        return None
    return v


def coerce_intent(v: Any) -> Any:
    # Coerce anything that isn't 'casual' to 'rag'
    if v == "casual":
        return "casual"
    return "rag"


def empty_str_to_unknown(v: Any) -> Any:
    if v == "":
        return "unknown"
    return v


class Citation(BaseModel):
    file_id: str
    file_name: Optional[str] = None
    node_id: Optional[str] = None
    page_number: Optional[int] = None
    quote: Optional[str] = None


class LLMOutput(BaseModel):
    answer_md: str = Field(
        description="The complete answer to the user's question in Markdown format.")
    intent: Annotated[Literal["casual", "rag"], BeforeValidator(coerce_intent)] = Field(
        description="Specifies if the intent was casual chat or RAG retrieval.")
    answer_type: Annotated[Literal[
        "direct_answer",
        "list_documents",
        "compare",
        "summarize",
        "unknown"
    ], BeforeValidator(empty_str_to_unknown)] = Field(description="The type of answer provided.")
    citations: List[Citation] = Field(
        default_factory=list, description="List of citations used in the answer.")
    listed_file_ids: List[str] = Field(
        default_factory=list, description="Deterministic list of file IDs if the answer list documents.")
    confidence: Annotated[Optional[Literal["low", "medium", "high"]], BeforeValidator(empty_str_to_none)] = Field(
        None, description="Model's confidence in the answer.")
    refused: bool = Field(
        False, description="True if the model refused to answer.")
    refusal_reason: Annotated[Optional[Literal["not_in_docs", "out_of_scope", "unsafe", "unknown"]], BeforeValidator(empty_str_to_none)] = Field(
        None, description="Reason for refusal.")
