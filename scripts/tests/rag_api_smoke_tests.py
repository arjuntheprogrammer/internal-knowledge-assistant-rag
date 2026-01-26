#!/usr/bin/env python3
"""
RAG API Smoke Tests.

This script performs high-level functional testing of the RAG API endpoints.
It authenticates with the backend and runs a series of predefined test cases
to ensure core functionality (chat, retrieval, etc.) is working as expected.

Usage:
    python3 scripts/tests/rag_api_smoke_tests.py
"""
import os
import sys
import time

from rag_test_utils import (
    get_auth_token,
    get_base_url,
    load_env,
    request_json,
    validate_response,
)


ENV_PATH = os.path.join(os.path.dirname(__file__), "..", "..", ".env")


TEST_CASES = [
    {
        "name": "case_01_single",
        "queries": ["hi"],
    },
    {
        "name": "case_02_double",
        "queries": [
            "list 5 documents",
            "list 3 stocks",
        ],
    },
]


def main():
    load_env(ENV_PATH)
    base_url = get_base_url()
    token = get_auth_token(base_url)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    print(f"Using API base: {base_url}")
    total_queries = sum(len(case["queries"]) for case in TEST_CASES)
    print(f"Running {len(TEST_CASES)} cases ({total_queries} queries).")

    failures = []
    query_index = 0
    for case in TEST_CASES:
        case_name = case["name"]
        queries = case["queries"]
        print(f"\n{case_name} ({len(queries)} queries)")
        for q_index, query in enumerate(queries, start=1):
            query_index += 1
            status, payload = request_json(
                "POST",
                f"{base_url}/api/chat/message",
                payload={"message": query},
                headers=headers,
            )
            ok, reason = validate_response(query, status, payload)
            status_label = "OK" if ok else "FAIL"
            print(f"[{query_index}/{total_queries}] {status_label}: {query}")
            if not ok:
                failures.append(
                    {
                        "case": case_name,
                        "query_index": q_index,
                        "query": query,
                        "reason": reason,
                        "status": status,
                        "payload": payload,
                    }
                )
            time.sleep(0.5)

    if failures:
        print("\nFailures:")
        for failure in failures:
            print(
                f"- {failure['case']} query {failure['query_index']}: "
                f"\"{failure['query']}\" -> {failure['reason']}"
            )
        sys.exit(1)

    print("\nAll smoke test cases passed.")


if __name__ == "__main__":
    main()
