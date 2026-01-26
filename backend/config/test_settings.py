import os
from pydantic_settings import BaseSettings


class TestSettings(BaseSettings):
    """Test-specific configuration managed via environment variables."""

    allow_env_openai_key_for_tests: bool = os.getenv(
        "ALLOW_ENV_OPENAI_KEY_FOR_TESTS", "false").lower() == "true"
    opik_eval_project_name: str = os.getenv(
        "OPIK_EVAL_PROJECT_NAME", "internal-knowledge-assistant-eval")
    opik_enabled: bool = os.getenv(
        "OPIK_ENABLED", "true").lower() not in ("false", "0", "no")

    # Dataset defaults
    default_dataset_name: str = "stock_eval_v1"

    class Config:
        case_sensitive = False


test_settings = TestSettings()
