"""
Custom Opik metrics for RAG evaluation.
Wraps deterministic metric functions from .metrics into Opik BaseMetric classes.
"""

import logging
from typing import Any, Dict, List, Optional

try:
    from opik.evaluation.metrics.score_result import ScoreResult
    from opik.evaluation.metrics.base_metric import BaseMetric
except ImportError:
    # Fallback for environments without opik
    class BaseMetric:
        def __init__(self, name: str):
            self.name = name

    class ScoreResult:
        def __init__(
            self,
            name: str,
            value: float,
            reason: Optional[str] = None,
            scoring_failed: bool = False
        ):
            self.name = name
            self.value = value
            self.reason = reason
            self.scoring_failed = scoring_failed

from .metrics import (
    compute_recall_at_k,
    compute_recall_all_at_k,
    detect_sources_section,
    count_citations,
    detect_refusal,
    check_refusal_correctness
)

logger = logging.getLogger(__name__)


class RecallAt5Metric(BaseMetric):
    def __init__(self):
        super().__init__(name="Recall@5")

    def score(self, output: str, expected_output: Dict[str, Any], **kwargs: Any) -> ScoreResult:
        expected_ids = expected_output.get("expected_file_ids", [])
        retrieved_ids = kwargs.get("retrieved_file_ids", [])

        value = compute_recall_at_k(expected_ids, retrieved_ids, 5)
        return ScoreResult(name=self.name, value=value)


class RecallAt10Metric(BaseMetric):
    def __init__(self):
        super().__init__(name="Recall@10")

    def score(self, output: str, expected_output: Dict[str, Any], **kwargs: Any) -> ScoreResult:
        expected_ids = expected_output.get("expected_file_ids", [])
        retrieved_ids = kwargs.get("retrieved_file_ids", [])

        value = compute_recall_at_k(expected_ids, retrieved_ids, 10)
        return ScoreResult(name=self.name, value=value)


class RecallAllAt5Metric(BaseMetric):
    def __init__(self):
        super().__init__(name="Recall-All@5")

    def score(self, output: str, expected_output: Dict[str, Any], **kwargs: Any) -> ScoreResult:
        expected_ids = expected_output.get("expected_file_ids", [])
        retrieved_ids = kwargs.get("retrieved_file_ids", [])

        value = compute_recall_all_at_k(expected_ids, retrieved_ids, 5)
        return ScoreResult(name=self.name, value=value)


class RecallAllAt10Metric(BaseMetric):
    def __init__(self):
        super().__init__(name="Recall-All@10")

    def score(self, output: str, expected_output: Dict[str, Any], **kwargs: Any) -> ScoreResult:
        expected_ids = expected_output.get("expected_file_ids", [])
        retrieved_ids = kwargs.get("retrieved_file_ids", [])

        value = compute_recall_all_at_k(expected_ids, retrieved_ids, 10)
        return ScoreResult(name=self.name, value=value)


class HasSourcesMetric(BaseMetric):
    def __init__(self):
        super().__init__(name="Has Sources Section")

    def score(self, output: str, **kwargs: Any) -> ScoreResult:
        has_sources = detect_sources_section(output)
        return ScoreResult(name=self.name, value=1.0 if has_sources else 0.0)


class CitationComplianceMetric(BaseMetric):
    def __init__(self):
        super().__init__(name="Citation Compliance")

    def score(self, output: str, expected_output: Dict[str, Any], **kwargs: Any) -> ScoreResult:
        text = output or ""
        expected_count = expected_output.get("required_citations_count", 0)

        # Use structured data if available
        structured = kwargs.get("structured", {})
        if structured.get("is_structured"):
            actual_count = structured.get("citations_count", 0)
            has_sources = actual_count > 0  # Simplified for structured
        else:
            has_sources = detect_sources_section(text)
            actual_count = count_citations(text)

        score = 0.0
        reasons = []

        if has_sources:
            score += 0.5
        else:
            reasons.append("Missing Sources section")

        if actual_count >= expected_count:
            score += 0.5
        else:
            reasons.append(
                f"Citation count {actual_count} < expected {expected_count}")

        return ScoreResult(
            name=self.name,
            value=score,
            reason=", ".join(reasons) if reasons else "Compliant"
        )


class RefusalCorrectMetric(BaseMetric):
    def __init__(self):
        super().__init__(name="Refusal Correctness")

    def score(self, output: str, expected_output: Dict[str, Any], **kwargs: Any) -> ScoreResult:
        must_refuse = expected_output.get("must_refuse", False)
        text = output or ""

        # Use structured data if available
        structured = kwargs.get("structured", {})
        if structured.get("is_structured"):
            refusal_detected = structured.get("refused", False)
        else:
            refusal_detected = detect_refusal(text)

        is_correct = check_refusal_correctness(
            must_refuse, refusal_detected, text)

        if must_refuse:
            return ScoreResult(
                name=self.name,
                value=1.0 if is_correct else 0.0,
                reason="Correctly refused" if is_correct else "Failed refusal check"
            )
        else:
            # If must_refuse is False, check_refusal_correctness returns None.
            # We want to penalize false positive refusals.
            if refusal_detected:
                return ScoreResult(name=self.name, value=0.0, reason="Refused unexpectedly")
            else:
                return ScoreResult(name=self.name, value=1.0, reason="Correctly answered")
