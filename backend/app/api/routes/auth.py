
import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from fastapi import APIRouter, Cookie, HTTPException, Response, status, Depends
from pymongo.errors import DuplicateKeyError
from pwdlib import PasswordHash

from app.db.mongodb import db
from app.schemas.auth import RegisterRequest, LoginRequest, UserResponse
from app.api.dependencies import (
    SESSION_COOKIE_NAME,
    get_current_user,
    hash_session_token,
)


router = APIRouter(prefix="/api/auth", tags=["Authentication"])
password_hasher = PasswordHash.recommended()

SESSION_DURATION_DAYS = 7
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=7 * 24 * 60 * 60,
        httponly=True,
        secure=False,
        samesite="lax",
        path="/",
    )


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_user(payload: RegisterRequest):
    username = payload.username.strip()

    if not username:
        raise HTTPException(
            status_code=422,
            detail="Username cannot be empty.",
        )

    user_document = {
        "username": username,
        "password_hash": password_hasher.hash(payload.password),
        "created_at": datetime.now(timezone.utc),
    }

    try:
        result = db["users"].insert_one(user_document)
    except DuplicateKeyError:
        raise HTTPException(
            status_code=409,
            detail="Username already exists.",
        )

    return UserResponse(
        id=str(result.inserted_id),
        username=username,
    )


@router.post("/login")
def login_user(payload: LoginRequest, response: Response):
    username = payload.username.strip()
    user = db["users"].find_one({"username": username})

    if user is None or not password_hasher.verify(
        payload.password,
        user["password_hash"],
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password.",
        )

    # Generate a random, opaque session ID.
    session_token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=SESSION_DURATION_DAYS)

    # Store only the hash in MongoDB, never the raw cookie value.
    db["sessions"].insert_one({
        "token_hash": hash_session_token(session_token),
        "user_id": user["_id"],
        "created_at": now,
        "expires_at": expires_at,
    })

    set_session_cookie(response, session_token)

    return {
        "message": "Login successful.",
        "user": {
            "id": str(user["_id"]),
            "username": user["username"],
        },
    }


@router.get("/me")
def get_me(user: dict = Depends(get_current_user)):
    return {"user": user}


@router.post("/logout")
def logout_user(
    response: Response,
    session_token: str | None = Cookie(
        default=None,
        alias=SESSION_COOKIE_NAME,
    ),
):
    if session_token:
        db["sessions"].delete_one({
            "token_hash": hash_session_token(session_token)
        })

    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
    )

    return {"message": "Logout successful."}
