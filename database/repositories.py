from datetime import datetime, timezone
from bson import ObjectId
from database.db_connection import DatabaseConnection

class BaseRepository:
    def __init__(self, collection_name: str):
        self._collection = DatabaseConnection().db[collection_name]

class CountryRepository(BaseRepository):
    def __init__(self):
        super().__init__("countries")

    def get_all(self, search: str = "", min_tier: int = 1) -> list:
        query = {"base_soldiers": {"$gte": int(min_tier)}}
        if search:
            query["name"] = {"$regex": search, "$options": "i"}
        return list(self._collection.find(query, {"_id": 0}).sort("population", -1))

    def get_by_name(self, name: str) -> dict:
        return self._collection.find_one({"name": name}, {"_id": 0})

    def seed_if_empty(self, countries_data: list):
        if self._collection.count_documents({}) == 0:
            self._collection.insert_many(countries_data)

class UserRepository(BaseRepository):
    def __init__(self):
        super().__init__("users")

    def create_user(self, username: str, password_hash: str) -> dict:
        user_doc = {
            "username": username,
            "password_hash": password_hash,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "games_played": 0,
            "games_won": 0
        }
        self._collection.insert_one(user_doc)
        return user_doc

    def find_by_username(self, username: str) -> dict:
        return self._collection.find_one({"username": username})

    def increment_stats(self, username: str, won: bool = False):
        inc_data = {"games_played": 1}
        if won:
            inc_data["games_won"] = 1
        self._collection.update_one({"username": username}, {"$inc": inc_data})

class GameSessionRepository(BaseRepository):
    def __init__(self):
        super().__init__("game_sessions")

    def create_session(self, state_dict: dict) -> str:
        result = self._collection.insert_one(state_dict)
        return str(result.inserted_id)

    def get_session(self, game_id: str) -> dict:
        doc = self._collection.find_one({"_id": ObjectId(game_id)})
        if doc:
            doc["game_id"] = str(doc.pop("_id"))
        return doc

    def update_session(self, game_id: str, state_dict: dict):
        state_copy = {k: v for k, v in state_dict.items() if k != "game_id"}
        state_copy["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._collection.update_one({"_id": ObjectId(game_id)}, {"$set": state_copy})

    def list_sessions(self, owner: str = None, status: str = None, search: str = None) -> list:
        query = {}
        if owner:
            query["owner_username"] = owner
        if status and status != "ALL":
            query["status"] = status
        if search:
            query["player_country"] = {"$regex": search, "$options": "i"}
        cursor = self._collection.find(query).sort("updated_at", -1).limit(50)
        results = []
        for doc in cursor:
            doc["game_id"] = str(doc.pop("_id"))
            results.append(doc)
        return results

    def get_platform_analytics(self) -> dict:
        """Platform-wide game analytics (totals and top commanders by win count)."""
        total_games = self._collection.count_documents({})
        completed_games = self._collection.count_documents({"status": "COMPLETED"})
        active_games = self._collection.count_documents({"status": "ACTIVE"})
        pipeline = [
            {"$match": {"status": "COMPLETED"}},
            {"$group": {"_id": "$winner_name", "wins": {"$sum": 1}}},
            {"$sort": {"wins": -1}},
            {"$limit": 5}
        ]
        top_commanders = list(self._collection.aggregate(pipeline))
        return {
            "total_games": total_games,
            "completed_games": completed_games,
            "active_games": active_games,
            "top_commanders": top_commanders
        }