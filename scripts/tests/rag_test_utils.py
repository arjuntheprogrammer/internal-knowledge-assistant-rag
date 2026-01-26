"""
RAG Test Utilities.

This module provides shared helper functions for the RAG testing suite,
including authentication token retrieval, API request handling, response
validation, and environment loading.
"""
import json
import os
import re
import urllib.error
import urllib.request


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
    req = urllib.request.Request(
        url, data=data, headers=headers or {}, method=method)
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
    token = (
        os.environ.get("FIREBASE_ID_TOKEN")
        or os.environ.get("AUTH_TOKEN")
        or os.environ.get("JWT_TOKEN")
    )
    if token:
        return token
    raise RuntimeError(
        "Set FIREBASE_ID_TOKEN (or AUTH_TOKEN) to run the tests against Firebase auth."
    )


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
