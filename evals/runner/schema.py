"""
Evaluation data schema definitions.
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class EvalSample:
    """Input sample from the evaluation dataset."""

    id: str
    query: str
    intent: str
    expected_file_ids: List[str] = field(default_factory=list)
    must_cite: bool = False
    required_citations_count: int = 0
    answer_style: str = "paragraph"
    max_entities: int = 0
    is_out_of_scope: bool = False
    must_refuse: bool = False
    no_external_knowledge: bool = True
    allowed_uncertainty: bool = False

    @classmethod
    def from_dict(cls, data: dict) -> "EvalSample":
        return cls(
            id=data.get("id", ""),
            query=data.get("query", ""),
            intent=data.get("intent", ""),
            expected_file_ids=data.get("expected_file_ids", []),
            must_cite=data.get("must_cite", False),
            required_citations_count=data.get("required_citations_count", 0),
            answer_style=data.get("answer_style", "paragraph"),
            max_entities=data.get("max_entities", 0),
            is_out_of_scope=data.get("is_out_of_scope", False),
            must_refuse=data.get("must_refuse", False),
            no_external_knowledge=data.get("no_external_knowledge", True),
            allowed_uncertainty=data.get("allowed_uncertainty", False),
        )


@dataclass
class EvalResult:
    """Output result for a single evaluation sample."""

    sample_id: str
    query: str
    intent: str
    expected_file_ids: List[str]
    answer_text: str = ""
    retrieved_node_ids: List[str] = field(default_factory=list)
    retrieved_file_ids: List[str] = field(default_factory=list)
    citation_file_ids: List[str] = field(default_factory=list)
    latency_ms: float = 0.0
    error: Optional[str] = None

    # Computed metrics
    recall_at_5: float = 0.0
    recall_at_10: float = 0.0
    recall_all_at_5: float = 0.0
    recall_all_at_10: float = 0.0
    has_sources_section: bool = False
    citation_count: int = 0
    citation_count_ok: bool = False
    cites_expected: bool = False
    refusal_detected: bool = False
    refusal_correct: Optional[bool] = None
    max_entities_ok: Optional[bool] = None

    def to_dict(self) -> dict:
        return {
            "sample_id": self.sample_id,
            "query": self.query,
            "intent": self.intent,
            "expected_file_ids": self.expected_file_ids,
            "answer_text": self.answer_text,
            "retrieved_node_ids": self.retrieved_node_ids,
            "retrieved_file_ids": self.retrieved_file_ids,
            "citation_file_ids": self.citation_file_ids,
            "latency_ms": self.latency_ms,
            "error": self.error,
            "recall_at_5": self.recall_at_5,
            "recall_at_10": self.recall_at_10,
            "recall_all_at_5": self.recall_all_at_5,
            "recall_all_at_10": self.recall_all_at_10,
            "has_sources_section": self.has_sources_section,
            "citation_count": self.citation_count,
            "citation_count_ok": self.citation_count_ok,
            "cites_expected": self.cites_expected,
            "refusal_detected": self.refusal_detected,
            "refusal_correct": self.refusal_correct,
            "max_entities_ok": self.max_entities_ok,
        }


@dataclass
class EvalSummary:
    """Summary statistics for an evaluation run."""

    total_samples: int = 0
    successful_samples: int = 0
    failed_samples: int = 0
    mean_latency_ms: float = 0.0
    mean_recall_at_5: float = 0.0
    mean_recall_at_10: float = 0.0
    mean_recall_all_at_5: float = 0.0
    mean_recall_all_at_10: float = 0.0
    cite_compliance_rate: float = 0.0
    refusal_correctness_rate: float = 0.0
    cite_samples_count: int = 0
    refusal_samples_count: int = 0

    def to_dict(self) -> dict:
        return {
            "total_samples": self.total_samples,
            "successful_samples": self.successful_samples,
            "failed_samples": self.failed_samples,
            "mean_latency_ms": self.mean_latency_ms,
            "mean_recall_at_5": self.mean_recall_at_5,
            "mean_recall_at_10": self.mean_recall_at_10,
            "mean_recall_all_at_5": self.mean_recall_all_at_5,
            "mean_recall_all_at_10": self.mean_recall_all_at_10,
            "cite_compliance_rate": self.cite_compliance_rate,
            "refusal_correctness_rate": self.refusal_correctness_rate,
            "cite_samples_count": self.cite_samples_count,
            "refusal_samples_count": self.refusal_samples_count,
        }
