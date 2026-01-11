from llama_index.core import Settings
from llama_index.core.callbacks import CallbackManager
from llama_index.llms.openai import OpenAI
from llama_index.embeddings.openai import OpenAIEmbedding
from backend.models.config import SystemConfig
from backend.services.langsmith_tracing import get_langsmith_callback_handler
import os


def get_service_context():
    config = SystemConfig.get_config()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OpenAI API Key not found")
    llm = OpenAI(model=config.get("openai_model", "gpt-4o-mini"))
    embed_model = OpenAIEmbedding(model="text-embedding-3-small")

    handler = get_langsmith_callback_handler()
    callback_manager = CallbackManager([handler]) if handler else None

    Settings.llm = llm
    Settings.embed_model = embed_model
    Settings.callback_manager = callback_manager
    return Settings
