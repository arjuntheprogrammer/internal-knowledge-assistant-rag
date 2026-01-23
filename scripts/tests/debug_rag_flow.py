"""
RAG Pipeline Debugger.

This script allows developers to step through the RAG pipeline execution by
running a sample query. It mocks the user context and sets up the environment
to trigger either casual or knowledge base tools.

Usage:
    PYTHONPATH=. python scripts/tests/debug_rag_flow.py
"""
from backend.services.rag import RAGService
import os
import sys
import logging
from dotenv import load_dotenv
import warnings

# Suppress annoying library-level warnings
warnings.filterwarnings("ignore", category=UserWarning, module="pymilvus")
warnings.filterwarnings("ignore", message="The 'validate_default' attribute")

# 1. Add repo root to path so we can import backend
sys.path.append(os.getcwd())


# Setup minimal logging to see the routing
logging.basicConfig(level=logging.INFO)


def debug_query():
    load_dotenv()

    # 2. Mock User Context
    # Ensure your .env has OPENAI_API_KEY, MILVUS_URI, etc.
    user_context = {
        "uid": "NUsot0aGhVMGEEnu9RujAPSRXtv2",  # Default test user
        "openai_api_key": os.getenv("OPENAI_API_KEY")
    }

    # 3. Enable environment keys for testing
    os.environ["ALLOW_ENV_OPENAI_KEY_FOR_TESTS"] = "true"

    question = "Which companies have the highest return on equity?"

    print(f"\n>>> Starting Debug Query: {question}")

    # 4. Run the query
    # SET A BREAKPOINT in backend/services/rag/engines.py
    # at the function: build_rag_query_engine
    result = RAGService.query(
        question,
        user_context,
        return_structured=True
    )

    print("\n>>> Query Finished. Result Intent:",
          result.get("llm", {}).get("intent"))
    print(">>> Answer Preview:", result.get(
        "llm", {}).get("answer_md")[:100] + "...")


if __name__ == "__main__":
    debug_query()
