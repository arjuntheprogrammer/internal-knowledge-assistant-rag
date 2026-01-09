from llama_index import ServiceContext
from llama_index.callbacks import CallbackManager
from llama_index.llms import OpenAI, Ollama
from backend.models.config import SystemConfig
from backend.services.langsmith_tracing import get_langsmith_callback_handler
import os


def get_service_context():
    config = SystemConfig.get_config()
    if config["llm_provider"] == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OpenAI API Key not found")
        llm = OpenAI(model=config.get("openai_model", "gpt-3.5-turbo"))
    else:
        llm = Ollama(
            base_url=config.get("ollama_url", "http://localhost:11434"),
            model=config.get("ollama_model", "llama2"),
        )

    handler = get_langsmith_callback_handler()
    callback_manager = CallbackManager([handler]) if handler else None
    return ServiceContext.from_defaults(llm=llm, callback_manager=callback_manager)
