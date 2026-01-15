import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "your_secret_key_here")
    UPLOAD_FOLDER = os.path.join(os.getcwd(), "backend/uploads")

    # Firebase Client Config - use property accessors to read at access time
    # This is necessary because secrets are loaded after config.py is imported
    @property
    def FIREBASE_API_KEY(self):
        return os.getenv("FIREBASE_API_KEY")

    @property
    def FIREBASE_AUTH_DOMAIN(self):
        return os.getenv("FIREBASE_AUTH_DOMAIN")

    @property
    def FIREBASE_PROJECT_ID(self):
        return os.getenv("FIREBASE_PROJECT_ID")

    @property
    def FIREBASE_STORAGE_BUCKET(self):
        return os.getenv("FIREBASE_STORAGE_BUCKET")

    @property
    def FIREBASE_MESSAGING_SENDER_ID(self):
        return os.getenv("FIREBASE_MESSAGING_SENDER_ID")

    @property
    def FIREBASE_APP_ID(self):
        return os.getenv("FIREBASE_APP_ID")


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
