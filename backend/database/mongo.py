"""MongoDB access. The app starts even if MongoDB is down; routes report the failure clearly."""
import os
from pymongo import MongoClient
from pymongo.errors import PyMongoError

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = os.getenv("MONGO_DB", "smartreview")

_client = None


def get_client() -> MongoClient:
    global _client
    if _client is None:
        _client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=1500)
    return _client


def get_db():
    return get_client()[DB_NAME]


def ping():
    try:
        get_client().admin.command("ping")
        return True, None
    except PyMongoError as exc:
        return False, f"MongoDB unreachable at {MONGO_URI}: {exc.__class__.__name__}"


class DatabaseUnavailable(Exception):
    pass


def require_db():
    ok, err = ping()
    if not ok:
        raise DatabaseUnavailable(err)
    return get_db()
