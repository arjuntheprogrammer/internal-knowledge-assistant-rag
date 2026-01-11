import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "your_secret_key_here")
    MONGO_URI = os.getenv(
        "MONGO_URI", "mongodb://localhost:27017/internal_knowledge_db"
    )
    UPLOAD_FOLDER = os.path.join(os.getcwd(), "backend/uploads")
    LLM_API_KEY = os.getenv("OPENAI_API_KEY")


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
