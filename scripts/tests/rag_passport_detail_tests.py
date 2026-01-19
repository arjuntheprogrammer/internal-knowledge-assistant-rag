#!/usr/bin/env python3
import os
import re
import sys
import time

from rag_test_utils import (
    get_auth_token,
    get_base_url,
    load_env,
    request_json,
)

ENV_PATH = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
DRIVE_FOLDER_ID = "1OrKd_1MOElmvyvKTkIm9c576SEOU2Pqg"

TEST_CASES = [
    {
        "name": "varsha_full_name",
        "query": "What is the full name on Varsha's passport?",
        "patterns": [r"\bVARSHA\b", r"\bAGGARWAL\b"],
    },
    {
        "name": "varsha_dob",
        "query": "What is Varsha's date of birth as written on the passport?",
        "patterns": [r"\b0?5/0?6/1996\b"],
    },
    {
        "name": "varsha_address",
        "query": "What is the address on Varsha's passport?",
        "patterns": [r"CIVIL\s+LINES", r"ROORKEE", r"UTTARAKHAND"],
    },
    {
        "name": "varsha_issue_date",
        "query": "What is Varsha's passport issue date?",
        "patterns": [r"\b28/12/2023\b"],
    },
    {
        "name": "varsha_expiry_date",
        "query": "What is Varsha's passport expiry date?",
        "patterns": [r"\b27/12/2033\b"],
    },
]


def get_indexing_ready(base_url, headers):
    status, payload = request_json("GET", f"{base_url}/api/config", headers=headers)
    if status != 200:
        raise RuntimeError(f"Failed to get indexing status: HTTP {status} {payload}")
    return {"ready": bool(payload.get("config_ready")), "status": payload.get("indexing", {}).get("status"), "message": payload.get("indexing", {}).get("message")}


def get_config(base_url, headers):
    status, payload = request_json("GET", f"{base_url}/api/config", headers=headers)
    if status != 200:
        raise RuntimeError(f"Failed to get config: HTTP {status} {payload}")
    return payload


def assert_patterns(response_text, patterns, case_name):
    if not response_text or not response_text.strip():
        return f"{case_name}: empty response"
    lowered = response_text.lower()
    if "couldn't find" in lowered or "could not find" in lowered:
        return f"{case_name}: response indicates missing info"
    for pattern in patterns:
        if not re.search(pattern, response_text, re.I | re.M):
            return f"{case_name}: missing pattern {pattern}"
    return None


def main():
    load_env(ENV_PATH)
    base_url = get_base_url()
    token = get_auth_token(base_url)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    print(f"Using API base: {base_url}")
    config = get_config(base_url, headers)
    drive_folder_id = config.get("drive_folder_id")
    if drive_folder_id and drive_folder_id != DRIVE_FOLDER_ID:
        print(
            "Warning: drive_folder_id does not match expected test folder. "
            f"Got {drive_folder_id}, expected {DRIVE_FOLDER_ID}."
        )

    status = get_indexing_ready(base_url, headers)
    if not status.get("ready"):
        raise RuntimeError(
            f"Indexing not ready: {status.get('status')} {status.get('message')}"
        )

    failures = []
    for idx, case in enumerate(TEST_CASES, start=1):
        query = case["query"]
        print(f"[{idx}/{len(TEST_CASES)}] {case['name']}: {query}")
        status_code, payload = request_json(
            "POST",
            f"{base_url}/api/chat/message",
            payload={"message": query},
            headers=headers,
        )
        if status_code != 200:
            failures.append(f"{case['name']}: HTTP {status_code} {payload}")
            continue
        response_text = payload.get("response") or ""
        error = assert_patterns(response_text, case["patterns"], case["name"])
        if error:
            failures.append(error)
        time.sleep(0.5)

    if failures:
        print("\nFailures:")
        for failure in failures:
            print(f"- {failure}")
        sys.exit(1)

    print("\nPassport detail tests passed.")


if __name__ == "__main__":
    main()
