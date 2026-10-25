
import hashlib
from datetime import datetime, timezone

from fastapi import Cookie, HTTPException, status
from bson import ObjectId

from app.db.mongodb import db


SESSION_COOKIE_NAME = "bookwise_session"


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def get_current_user(
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
):
    """Return the authenticated user or reject the request."""

    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    token_hash = hash_session_token(session_token)

    session = db["sessions"].find_one({"token_hash": token_hash})

    if session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session is invalid or expired.",
        )

    expires_at = session["expires_at"]

    # PyMongo may return naive UTC datetimes by default.
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at <= datetime.now(timezone.utc):
        db["sessions"].delete_one({"_id": session["_id"]})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session is expired.",
        )

    user = db["users"].find_one({"_id": session["user_id"]})

    if user is None:
        db["sessions"].delete_one({"_id": session["_id"]})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer exists.",
        )

    return {
        "id": str(user["_id"]),
        "username": user["username"],
    }
