from backend.services.db import Database
from datetime import datetime


class SystemConfig:
    @staticmethod
    def get_config():
        db = Database.get_db()
        config = db.config.find_one({"_id": "system_config"})
        if not config:
            # Default config
            default_config = {
                "_id": "system_config",
                "openai_model": "gpt-4o-mini",
                "drive_folders": [],  # List of {'id': '...', 'name': '...'}
                "updated_at": datetime.utcnow(),
            }
            db.config.insert_one(default_config)
            return default_config
        return config

    @staticmethod
    def update_config(data):
        db = Database.get_db()
        update_data = {k: v for k, v in data.items() if k != "_id"}
        update_data["updated_at"] = datetime.utcnow()
        db.config.update_one(
            {"_id": "system_config"}, {"$set": update_data}, upsert=True
        )
        return True
