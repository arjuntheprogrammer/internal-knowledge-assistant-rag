from pymongo import MongoClient
from config import config
import os

class Database:
    client = None
    db = None

    @classmethod
    def initialize(cls):
        config_name = os.getenv('FLASK_CONFIG') or 'default'
        mongo_uri = config[config_name].MONGO_URI
        cls.client = MongoClient(mongo_uri)
        cls.db = cls.client.get_database()
        print(f"Connected to MongoDB: {cls.db.name}")

    @classmethod
    def get_db(cls):
        if cls.db is None:
            cls.initialize()
        return cls.db
