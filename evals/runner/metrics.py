"""
Evaluation metrics for RAG system.
All metrics are deterministic (no LLM judging).
"""

import re
from typing import List, Optional, Set

from .schema import EvalResult, EvalSample, EvalSummary


# Refusal detection patterns
REFUSAL_PATTERNS = [
    r"couldn['\u2019]t find",
    r"could not find",
    r"not in your documents",
    r"not available in the provided documents",
    r"only able to answer based on",
    r"I['\u2019]m sorry,? I couldn['\u2019]t find",
    r"unable to find",
    r"no information",
    r"insufficient information",
]


def compute_recall_at_k(
    expected: List[str], retrieved: List[str], k: int
) -> float:
    """
    Compute Recall@k: 1 if any expected ID appears in top-k retrieved, else 0.
    """
    if not expected:
        return 1.0  # No expected items means perfect recall
    retrieved_top_k = set(retrieved[:k])
    for exp_id in expected:
        if exp_id in retrieved_top_k:
            return 1.0
    return 0.0


def compute_recall_all_at_k(
    expected: List[str], retrieved: List[str], k: int
) -> float:
    """
    Compute fraction of expected IDs present in top-k retrieved.
    Useful for multi-doc queries (compare intents).
    """
    if not expected:
        return 1.0
    retrieved_top_k = set(retrieved[:k])
    hits = sum(1 for exp_id in expected if exp_id in retrieved_top_k)
    return hits / len(expected)


def detect_sources_section(answer_text: str) -> bool:
    """Check if the answer contains a Sources section (### Sources or **Sources:**)."""
    if not answer_text:
        return False
    # Support both markdown header and bolded text
    return bool(re.search(r"(?:###|\*\*)\s*Sources\s*(?::|)", answer_text, re.IGNORECASE))


def count_citations(answer_text: str) -> int:
    """
    Count the number of citation items in the Sources section.
    Looks for bullet points after **Sources:**
    """
    if not answer_text:
        return 0
    match = re.search(
        r"(?:###|\*\*)\s*Sources\s*(?::|)\s*(.*)", answer_text, re.IGNORECASE | re.DOTALL
    )
    if not match:
        return 0
    sources_text = match.group(1)
    # Count bullet points (- or *)
    bullets = re.findall(r"(?m)^\s*[-*]\s+", sources_text)
    return len(bullets) if bullets else (1 if sources_text.strip() else 0)


def check_cites_expected(
    expected_file_ids: List[str],
    retrieved_file_ids: List[str],
    has_sources: bool,
) -> bool:
    """
    Check if any expected file ID is in retrieved and sources section exists.
    """
    if not has_sources or not expected_file_ids:
        return False
    retrieved_set = set(retrieved_file_ids)
    return any(exp_id in retrieved_set for exp_id in expected_file_ids)


def detect_refusal(answer_text: str) -> bool:
    """Detect if the answer contains refusal language."""
    if not answer_text:
        return False
    text_lower = answer_text.lower()
    for pattern in REFUSAL_PATTERNS:
        if re.search(pattern, text_lower):
            return True
    return False


def check_refusal_correctness(
    must_refuse: bool, refusal_detected: bool, answer_text: str
) -> Optional[bool]:
    """
    Check if refusal behavior is correct.
    Returns None if must_refuse is False.
    """
    if not must_refuse:
        return None
    # If must_refuse is True, we expect refusal_detected to be True
    # AND the answer should not contain fabricated specifics
    if not refusal_detected:
        return False
    # Simple heuristic: check for too many numbers (could be fabricated data)
    numbers = re.findall(r"\b\d+(?:\.\d+)?\b", answer_text)
    if len(numbers) > 5:
        # Too many numbers might indicate fabricated data
        return False
    return True


def extract_entity_names(text: str) -> Set[str]:
    """
    Extract capitalized multi-word phrases as potential entity names.
    Simple heuristic for max_entities check.
    """
    # Match capitalized words (at least 2 chars) with optional following words
    pattern = r"\b([A-Z][a-zA-Z]{1,}(?:\s+[A-Z][a-zA-Z]+)*)\b"
    matches = re.findall(pattern, text)
    # Filter out common words that might be capitalized
    common_words = {
        "The", "This", "That", "These", "Those", "What", "Where", "When",
        "How", "Why", "Which", "Who", "Answer", "Sources", "None", "Limited",
        "Company", "Corporation", "Ltd", "Inc", "Based", "According",
    }
    entities = set()
    for match in matches:
        words = match.split()
        if len(words) >= 2 or (len(words) == 1 and words[0] not in common_words):
            entities.add(match)
    return entities


def check_max_entities(
    answer_text: str, max_entities: int, allowed_entities: Set[str]
) -> Optional[bool]:
    """
    Check if the answer mentions too many distinct entities.
    Returns None if max_entities is 0 (no check).
    """
    if max_entities <= 0:
        return None
    if not answer_text:
        return True
    found_entities = extract_entity_names(answer_text)
    # Filter to only count entities that are in the allowed set
    relevant_entities = found_entities & allowed_entities if allowed_entities else found_entities
    return len(relevant_entities) <= max_entities


def compute_metrics(
    sample: EvalSample,
    result: EvalResult,
    allowed_entities: Optional[Set[str]] = None,
) -> EvalResult:
    """
    Compute all metrics for a single evaluation result.
    """
    if result.error:
        return result

    # Retrieval metrics
    result.recall_at_5 = compute_recall_at_k(
        sample.expected_file_ids, result.retrieved_file_ids, 5
    )
    result.recall_at_10 = compute_recall_at_k(
        sample.expected_file_ids, result.retrieved_file_ids, 10
    )
    result.recall_all_at_5 = compute_recall_all_at_k(
        sample.expected_file_ids, result.retrieved_file_ids, 5
    )
    result.recall_all_at_10 = compute_recall_all_at_k(
        sample.expected_file_ids, result.retrieved_file_ids, 10
    )

    # Citation metrics
    result.has_sources_section = detect_sources_section(result.answer_text)
    result.citation_count = count_citations(result.answer_text)
    result.citation_count_ok = result.citation_count >= sample.required_citations_count
    result.cites_expected = check_cites_expected(
        sample.expected_file_ids,
        result.retrieved_file_ids,
        result.has_sources_section,
    )

    # Refusal metrics
    result.refusal_detected = detect_refusal(result.answer_text)
    result.refusal_correct = check_refusal_correctness(
        sample.must_refuse, result.refusal_detected, result.answer_text
    )

    # Entity constraint metrics
    result.max_entities_ok = check_max_entities(
        result.answer_text, sample.max_entities, allowed_entities or set()
    )

    return result


def compute_summary(
    results: List[EvalResult], samples: List[EvalSample]
) -> EvalSummary:
    """
    Compute summary statistics for an evaluation run.
    """
    summary = EvalSummary()
    summary.total_samples = len(results)
    summary.successful_samples = sum(1 for r in results if r.error is None)
    summary.failed_samples = summary.total_samples - summary.successful_samples

    successful_results = [r for r in results if r.error is None]

    if successful_results:
        summary.mean_latency_ms = sum(r.latency_ms for r in successful_results) / len(
            successful_results
        )
        summary.mean_recall_at_5 = sum(r.recall_at_5 for r in successful_results) / len(
            successful_results
        )
        summary.mean_recall_at_10 = sum(
            r.recall_at_10 for r in successful_results
        ) / len(successful_results)
        summary.mean_recall_all_at_5 = sum(
            r.recall_all_at_5 for r in successful_results
        ) / len(successful_results)
        summary.mean_recall_all_at_10 = sum(
            r.recall_all_at_10 for r in successful_results
        ) / len(successful_results)

    # Citation compliance
    sample_map = {s.id: s for s in samples}
    cite_samples = [
        r
        for r in successful_results
        if sample_map.get(r.sample_id, EvalSample("", "", "")).must_cite
    ]
    summary.cite_samples_count = len(cite_samples)
    if cite_samples:
        cite_compliant = sum(
            1 for r in cite_samples if r.has_sources_section and r.cites_expected
        )
        summary.cite_compliance_rate = cite_compliant / len(cite_samples)

    # Refusal correctness
    refusal_samples = [
        r
        for r in successful_results
        if sample_map.get(r.sample_id, EvalSample("", "", "")).must_refuse
    ]
    summary.refusal_samples_count = len(refusal_samples)
    if refusal_samples:
        refusal_correct = sum(
            1 for r in refusal_samples if r.refusal_correct is True
        )
        summary.refusal_correctness_rate = refusal_correct / \
            len(refusal_samples)

    return summary
