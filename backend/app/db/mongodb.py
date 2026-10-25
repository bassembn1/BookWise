
import os

from pymongo import ASCENDING, MongoClient
from pymongo.database import Database
from datetime import datetime, timedelta, timezone

MONGO_URI = os.getenv(
    "MONGO_URI",
    "mongodb://localhost:27017"
)

client = MongoClient(
    MONGO_URI,
    serverSelectionTimeoutMS=5000
)

db: Database = client["bookwise"]


def check_mongodb_connection() -> bool:
    try:
        client.admin.command("ping")
        return True
    except Exception:
        return False


def ensure_indexes() -> None:
    """Create the indexes required by BookWise."""

    # Each username must be unique.
    db["users"].create_index(
        [("username", ASCENDING)],
        unique=True,
        name="unique_username"
    )

    # A user cannot add the same ISBN twice to their library.
    db["user_library"].create_index(
        [
            ("user_id", ASCENDING),
            ("isbn", ASCENDING)
        ],
        unique=True,
        name="unique_user_library_isbn"
    )

    # One rating per user per ISBN.
    db["ratings"].create_index(
        [
            ("user_id", ASCENDING),
            ("isbn", ASCENDING)
        ],
        unique=True,
        name="unique_user_rating"
    )
    db["sessions"].create_index(
    [("token_hash", ASCENDING)],
    unique=True,
    name="unique_session_token_hash",
    )

    db["sessions"].create_index(
        [("expires_at", ASCENDING)],
        expireAfterSeconds=0,
        name="expire_sessions",
    )

    db["sessions"].create_index(
        [("user_id", ASCENDING)],
        name="sessions_by_user",
    )
    


def close_mongodb_connection() -> None:
    client.close()
