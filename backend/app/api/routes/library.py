
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.errors import DuplicateKeyError

from app.api.dependencies import get_current_user
from app.db.mongodb import db
from app.schemas.library import AddBookRequest


router = APIRouter(
    prefix="/api/library",
    tags=["Personal Library"],
)


def get_user_object_id(current_user: dict) -> ObjectId:
    """Convert the authenticated user's ID to MongoDB ObjectId."""
    try:
        return ObjectId(current_user["id"])
    except (KeyError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user session.",
        )


def serialize_book(book: dict) -> dict:
    added_at = book.get("added_at")

    if isinstance(added_at, datetime):
        added_at = added_at.isoformat()
    elif added_at is None:
        added_at = ""

    return {
        "isbn": book["isbn"],
        "title": book["title"],
        "author": book.get("author", "Unknown"),
        "added_at": added_at,
    }


@router.get("")
def get_my_library(
    current_user: dict = Depends(get_current_user),
):
    user_id = get_user_object_id(current_user)

    books = db["user_library"].find(
        {"user_id": user_id}
    ).sort("added_at", -1)

    return {
        "count": db["user_library"].count_documents(
            {"user_id": user_id}
        ),
        "books": [serialize_book(book) for book in books],
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def add_book_to_library(
    payload: AddBookRequest,
    current_user: dict = Depends(get_current_user),
):
    user_id = get_user_object_id(current_user)

    isbn = "".join(
        char for char in payload.isbn.upper()
        if char.isdigit() or char == "X"
    )

    if len(isbn) not in (10, 13):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="ISBN must contain 10 or 13 valid characters.",
        )

    title = payload.title.strip()
    author = payload.author.strip() or "Unknown"

    if not title:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Book title cannot be empty.",
        )

    book_document = {
        "user_id": user_id,
        "isbn": isbn,
        "title": title,
        "author": author,
        "added_at": datetime.now(timezone.utc),
    }

    try:
        db["user_library"].insert_one(book_document)
    except DuplicateKeyError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This book is already in your library.",
        )

    return {
        "message": "Book added to your library.",
        "book": serialize_book(book_document),
    }


@router.delete("/{isbn}")
def remove_book_from_library(
    isbn: str,
    current_user: dict = Depends(get_current_user),
):
    user_id = get_user_object_id(current_user)

    clean_isbn = "".join(
        char for char in isbn.upper()
        if char.isdigit() or char == "X"
    )

    result = db["user_library"].delete_one({
        "user_id": user_id,
        "isbn": clean_isbn,
    })

    if result.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found in your library.",
        )

    return {"message": "Book removed from your library."}
