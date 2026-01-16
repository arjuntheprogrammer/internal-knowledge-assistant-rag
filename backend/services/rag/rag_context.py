from llama_index.core import Settings
from llama_index.core.callbacks import CallbackManager
from llama_index.llms.openai import OpenAI
from llama_index.embeddings.openai import OpenAIEmbedding
from backend.services.opik_tracing import get_opik_callback_handler
import os


def get_service_context(openai_api_key=None, user_id=None):
    api_key = openai_api_key
    if not api_key:
        allow_env = os.getenv("ALLOW_ENV_OPENAI_KEY_FOR_TESTS", "").lower() in {
            "1",
            "true",
            "yes",
        }
        if allow_env:
            api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OpenAI API Key not found")

    llm = OpenAI(model="gpt-4.1-mini", api_key=api_key)
    embed_model = OpenAIEmbedding(model="text-embedding-3-small", api_key=api_key)

    handler = get_opik_callback_handler(user_id=user_id)
    callback_manager = CallbackManager([handler]) if handler else None

    Settings.llm = llm
    Settings.embed_model = embed_model
    Settings.callback_manager = callback_manager
    return Settings
