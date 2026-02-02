from pymongo import MongoClient
import os

def init_mongo():
    mongo_uri = os.getenv("MONGO_URI")
    mongo_db = os.getenv("MONGO_DB", "marhaba")
    mongo_collection = os.getenv("MONGO_COLLECTION", "users")

    if not mongo_uri:
        return None, False, "MONGO_URI not set"

    try:
        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=3000)
        collection = client[mongo_db][mongo_collection]
        collection.create_index("email", unique=True)
        return collection, True, None
    except Exception as exc:
        return None, False, exc
