import os
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import ConnectionFailure
from dotenv import load_dotenv

load_dotenv()

class DatabaseConnection:
    """Singleton MongoDB Atlas connection manager — ensures one shared client/connection pool app-wide."""
    _instance = None
    _client = None
    _db = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DatabaseConnection, cls).__new__(cls)
            cls._instance._initialize_connection()
        return cls._instance

    def _initialize_connection(self):
        mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017/uct_geopolitics")
        try:
            self._client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
            self._client.admin.command("ping")
            db_name = os.getenv("MONGO_DB_NAME", "uct_geopolitics_2027")
            self._db = self._client[db_name]
            self._ensure_indexes()
        except ConnectionFailure as exc:
            raise RuntimeError(f"Failed to connect to MongoDB Atlas: {exc}")

    def _ensure_indexes(self):
        """Configures NoSQL indexes for fast searching and filtering."""
        self._db.users.create_index([("username", ASCENDING)], unique=True)
        self._db.countries.create_index([("name", ASCENDING)], unique=True)
        self._db.countries.create_index([("population", DESCENDING)])
        self._db.game_sessions.create_index([("owner_username", ASCENDING), ("status", ASCENDING)])
        self._db.battle_logs.create_index([("game_id", ASCENDING), ("timestamp", DESCENDING)])

    @property
    def db(self):
        return self._db