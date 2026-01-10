#!/usr/bin/env python3
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request


ENV_PATH = os.path.join(os.path.dirname(__file__), "..", ".env")


def load_env(path):
    if not os.path.exists(path):
        return
    with open(path, "r") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def request_json(method, url, payload=None, headers=None, timeout=120):
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body)
    except urllib.error.HTTPError as err:
        body = err.read().decode("utf-8")
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            payload = {"error": body}
        return err.code, payload
    except urllib.error.URLError as err:
        return 0, {"error": str(err)}


def get_base_url():
    base_url = os.environ.get("API_BASE_URL")
    if base_url:
        return base_url.rstrip("/")
    port = os.environ.get("PORT", "5001")
    return f"http://localhost:{port}"


def get_auth_token(base_url):
    token = os.environ.get("AUTH_TOKEN") or os.environ.get("JWT_TOKEN")
    if token:
        return token
    email = os.environ.get("ADMIN_EMAIL", "admin@gmail.com")
    password = os.environ.get("ADMIN_PASSWORD", "admin@gmail.com")
    status, payload = request_json(
        "POST",
        f"{base_url}/api/auth/login",
        payload={"email": email, "password": password},
        headers={"Content-Type": "application/json"},
    )
    if status != 200:
        raise RuntimeError(f"Login failed ({status}): {payload}")
    token = payload.get("token")
    if not token:
        raise RuntimeError("Login did not return a token.")
    return token


def expected_count_from_query(query):
    if not re.search(r"\b(list|show|provide|give|enumerate|top|bullet)\b", query, re.I):
        return None
    match = re.search(r"\b(\d{1,2})\b", query)
    if not match:
        return None
    return int(match.group(1))


def bullet_count_from_response(text):
    count = 0
    for line in text.splitlines():
        if re.match(r"^\s*[-*]\s+", line):
            count += 1
        elif re.match(r"^\s*\d+[\).]\s+", line):
            count += 1
    return count


def validate_response(query, status, payload):
    if status != 200:
        return False, f"HTTP {status}: {payload}"
    response_text = payload.get("response") or ""
    if not response_text.strip():
        return False, "Empty response body."
    lowered = response_text.lower()
    if "error processing request" in lowered or "empty response" in lowered:
        return False, "Response indicates an error or empty result."
    expected = expected_count_from_query(query)
    if expected:
        bullet_count = bullet_count_from_response(response_text)
        if bullet_count < expected:
            return (
                False,
                f"Expected at least {expected} items, got {bullet_count}.",
            )
    return True, ""


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
