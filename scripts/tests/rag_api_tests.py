#!/usr/bin/env python3
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
    {
        "name": "case_03_triple",
        "queries": [
            "What is HCL Technologies Limited known for?",
            "Summarize Sun Pharmaceutical Industries Limited in one sentence.",
            "What does Bharat Electronics Limited do?",
        ],
    },
    {
        "name": "case_04_quad",
        "queries": [
            "list all documents in the knowledge base",
            "Give a one-line description for Bajaj Auto Limited.",
            "Give a one-line description for Apollo Hospitals Enterprise Limited.",
            "What is the main business of HCL Technologies Limited?",
        ],
    },
    {
        "name": "case_05_five",
        "queries": [
            "provide 5 items from the knowledge base",
            "list 5 companies",
            "What sector is Sun Pharmaceutical Industries Limited in?",
            "Explain Bharat Electronics Limited in one sentence.",
            "What does Apollo Hospitals Enterprise Limited specialize in?",
        ],
    },
    {
        "name": "case_06_six",
        "queries": [
            "show 2 documents",
            "list 5 stocks",
            "Give a one-line description of Bajaj Auto Limited.",
            "Give a one-line description of Sun Pharmaceutical Industries Limited.",
            "Give a one-line description of Bharat Electronics Limited.",
            "Give a one-line description of HCL Technologies Limited.",
        ],
    },
    {
        "name": "case_07_seven",
        "queries": [
            "list 3 files in the drive folder",
            "What is Apollo Hospitals Enterprise Limited known for?",
            "Summarize Bajaj Auto Limited in one sentence.",
            "Summarize Sun Pharmaceutical Industries Limited in one sentence.",
            "Summarize Bharat Electronics Limited in one sentence.",
            "Summarize HCL Technologies Limited in one sentence.",
            "Summarize Apollo Hospitals Enterprise Limited in one sentence.",
        ],
    },
    {
        "name": "case_08_eight",
        "queries": [
            "list all files",
            "What is the focus of HCL Technologies Limited?",
            "What is the focus of Sun Pharmaceutical Industries Limited?",
            "What is the focus of Bharat Electronics Limited?",
            "What is the focus of Bajaj Auto Limited?",
            "What is the focus of Apollo Hospitals Enterprise Limited?",
            "list 5 documents",
            "list 4 stocks",
        ],
    },
    {
        "name": "case_09_nine",
        "queries": [
            "list 5 stocks from the knowledge base",
            "give 2 bullet points about Bajaj Auto Limited",
            "give 2 bullet points about HCL Technologies Limited",
            "give 2 bullet points about Sun Pharmaceutical Industries Limited",
            "give 2 bullet points about Bharat Electronics Limited",
            "give 2 bullet points about Apollo Hospitals Enterprise Limited",
            "What is the main business of Apollo Hospitals Enterprise Limited?",
            "What is the main business of Sun Pharmaceutical Industries Limited?",
            "What is the main business of Bajaj Auto Limited?",
        ],
    },
    {
        "name": "case_10_ten",
        "queries": [
            "list 5 documents from the drive",
            "What does HCL Technologies Limited do?",
            "What does Sun Pharmaceutical Industries Limited do?",
            "What does Bharat Electronics Limited do?",
            "What does Bajaj Auto Limited do?",
            "What does Apollo Hospitals Enterprise Limited do?",
            "Give a short summary of HCL Technologies Limited.",
            "Give a short summary of Sun Pharmaceutical Industries Limited.",
            "Give a short summary of Bharat Electronics Limited.",
            "Give a short summary of Apollo Hospitals Enterprise Limited.",
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

    print("\nAll test cases passed.")


if __name__ == "__main__":
    main()
