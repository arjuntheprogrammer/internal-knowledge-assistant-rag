from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class Citation(BaseModel):
    file_id: str
    file_name: Optional[str] = None
    node_id: Optional[str] = None
    page_number: Optional[int] = None
    quote: Optional[str] = None


class LLMOutput(BaseModel):
    answer_md: str = Field(
        description="The complete answer to the user's question in Markdown format.")
    intent: Literal["casual", "rag"] = Field(
        description="Specifies if the intent was casual chat or RAG retrieval.")
    answer_type: Literal[
        "direct_answer",
        "list_documents",
        "compare",
        "summarize",
        "unknown"
    ] = Field(description="The type of answer provided.")
    citations: List[Citation] = Field(
        default_factory=list, description="List of citations used in the answer.")
    listed_file_ids: List[str] = Field(
        default_factory=list, description="Deterministic list of file IDs if the answer list documents.")
    confidence: Optional[Literal["low", "medium", "high"]] = Field(
        None, description="Model's confidence in the answer.")
    refused: bool = Field(
        False, description="True if the model refused to answer.")
    refusal_reason: Optional[Literal["not_in_docs", "out_of_scope", "unsafe", "unknown"]] = Field(
        None, description="Reason for refusal.")
