""" 
from io import BytesIO

from fastapi import APIRouter, File, HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError

from app.ml.image_search import (
    extract_text_from_image,
    find_books,
)

router = APIRouter(
    prefix="/api/image-search",
    tags=["Image Search"],
)

MAX_FILE_SIZE = 8 * 1024 * 1024  # 8 MB
MAX_IMAGE_PIXELS = 20_000_000
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}


@router.post("")
def search_by_image(file: UploadFile = File(...)):
    
    #Upload a book cover, extract English text using OCR,
    #and search the existing book dataset.
    
    if file.content_type not in {
        "image/jpeg",
        "image/png",
        "image/webp",
    }:
        raise HTTPException(
            status_code=415,
            detail="Unsupported image type. Use JPEG, PNG, or WEBP.",
        )

    try:
        # Read at most 8 MB plus one byte to detect oversized files.
        content = file.file.read(MAX_FILE_SIZE + 1)

        if not content:
            raise HTTPException(
                status_code=400,
                detail="The uploaded image is empty.",
            )

        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail="Image is too large. Maximum size is 8 MB.",
            )

        try:
            with Image.open(BytesIO(content)) as source:
                if source.format not in ALLOWED_FORMATS:
                    raise HTTPException(
                        status_code=415,
                        detail="Unsupported image format.",
                    )

                width, height = source.size

                if width * height > MAX_IMAGE_PIXELS:
                    raise HTTPException(
                        status_code=413,
                        detail="Image dimensions are too large.",
                    )

                source.load()
                image = source.convert("RGB")

        except HTTPException:
            raise
        except (
            UnidentifiedImageError,
            OSError,
            Image.DecompressionBombError,
        ) as exc:
            raise HTTPException(
                status_code=400,
                detail="The uploaded file is not a valid supported image.",
            ) from exc

        try:
            detections = extract_text_from_image(image)
            books = find_books(detections)
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=500,
                detail="The books dataset could not be found.",
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=500,
                detail="The books dataset has an unexpected format.",
            ) from exc

        extracted_text = [
            item["text"] for item in detections
        ]

        return {
            "extracted_text": extracted_text,
            "detections": detections,
            "count": len(books),
            "books": books,
            "message": (
                "Search completed."
                if books
                else "No matching books were found. Try a clearer image."
            ),
        }

    finally:
        file.file.close()
 """
 
 
from io import BytesIO
from urllib.parse import quote

import pandas as pd
from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from PIL import Image, UnidentifiedImageError

from app.ml.image_search import (
    extract_text_from_image,
    find_books,
    normalize_text,
)

router = APIRouter(
    prefix="/api/image-search",
    tags=["Image Search"],
)

MAX_FILE_SIZE = 8 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}


def get_cover_url(isbn: str) -> str | None:
    """Build an Open Library cover URL from a book ISBN."""
    isbn = (isbn or "").strip()

    if not isbn:
        return None

    encoded_isbn = quote(isbn, safe="")
    return (
        f"https://covers.openlibrary.org/b/isbn/"
        f"{encoded_isbn}-M.jpg?default=false"
    )


def get_book_metadata(recommender, title: str) -> dict:
    """Return book metadata and a cover image URL."""
    books = recommender.df_books
    matches = books[books["title"] == title]

    if matches.empty:
        return {
            "isbn": "",
            "title": title,
            "author": "Unknown",
            "image_url": None,
        }

    row = matches.iloc[0]

    isbn_value = row.get("isbn", "")
    author_value = row.get("author", "Unknown")

    isbn = (
        str(isbn_value).strip()
        if pd.notna(isbn_value)
        else ""
    )

    author = (
        str(author_value).strip()
        if pd.notna(author_value) and str(author_value).strip()
        else "Unknown"
    )

    return {
        "isbn": isbn,
        "title": title,
        "author": author,
        "image_url": get_cover_url(isbn),
    }


@router.post("")
def search_by_image(
    request: Request,
    file: UploadFile = File(...),
):
    """
    Extract text from a book cover, find one matching book,
    and return recommendations from the existing KNN model.
    """

    if file.content_type not in {
        "image/jpeg",
        "image/png",
        "image/webp",
    }:
        raise HTTPException(
            status_code=415,
            detail="Unsupported image type. Use JPEG, PNG, or WEBP.",
        )

    try:
        content = file.file.read(MAX_FILE_SIZE + 1)

        if not content:
            raise HTTPException(
                status_code=400,
                detail="The uploaded image is empty.",
            )

        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail="Image is too large. Maximum size is 8 MB.",
            )

        try:
            with Image.open(BytesIO(content)) as source:
                if source.format not in ALLOWED_FORMATS:
                    raise HTTPException(
                        status_code=415,
                        detail="Unsupported image format.",
                    )

                width, height = source.size

                if width * height > MAX_IMAGE_PIXELS:
                    raise HTTPException(
                        status_code=413,
                        detail="Image dimensions are too large.",
                    )

                source.load()
                image = source.convert("RGB")

        except HTTPException:
            raise
        except (
            UnidentifiedImageError,
            OSError,
            Image.DecompressionBombError,
        ) as exc:
            raise HTTPException(
                status_code=400,
                detail="The uploaded file is not a valid supported image.",
            ) from exc

        try:
            detections = extract_text_from_image(image)
            candidates = find_books(detections, limit=10)
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=500,
                detail="The books dataset could not be found.",
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=500,
                detail="The books dataset has an unexpected format.",
            ) from exc

        extracted_text = [
            item["text"] for item in detections
        ]

        if not candidates:
            return {
                "extracted_text": extracted_text,
                "detections": detections,
                "matched_book": None,
                "recommendations": [],
                "count": 0,
                "message": (
                    "No matching books were found. "
                    "Try a clearer image with the title visible."
                ),
            }

        recommender = request.app.state.recommender
        model_titles = list(recommender.piv.index)

        # Map normalized titles to their real titles in the KNN model.
        normalized_model_titles = {}

        for model_title in model_titles:
            key = normalize_text(str(model_title))
            if key and key not in normalized_model_titles:
                normalized_model_titles[key] = model_title

        # Prefer the highest-ranked OCR candidate that exists in KNN.
        selected_candidate = None
        selected_model_title = None

        for candidate in candidates:
            candidate_title = candidate["title"]

            if candidate_title in recommender.piv.index:
                selected_candidate = candidate
                selected_model_title = candidate_title
                break

            normalized_title = normalize_text(candidate_title)
            model_title = normalized_model_titles.get(normalized_title)

            if model_title is not None:
                selected_candidate = candidate
                selected_model_title = model_title
                break

        # If OCR found a book but it isn't in KNN, still show one book.
        if selected_candidate is None:
            selected_candidate = candidates[0]

            matched_book = {
                "isbn": selected_candidate.get("isbn", ""),
                "title": selected_candidate["title"],
                "author": selected_candidate.get("author", "Unknown"),
                "match_score": selected_candidate.get("match_score", 0),
                "image_url": get_cover_url(
                    selected_candidate.get("isbn", "")
                ),
            }

            return {
                "extracted_text": extracted_text,
                "detections": detections,
                "matched_book": matched_book,
                "recommendations": [],
                "count": 0,
                "message": (
                    "A matching book was found, but it is not included "
                    "in the current KNN recommendation model."
                ),
            }

        # Get metadata for the exact title used by the KNN model.
        matched_book = get_book_metadata(
            recommender,
            selected_model_title,
        )
        matched_book["match_score"] = selected_candidate.get(
            "match_score", 0
        )

        try:
            _, knn_results = recommender.get_recommends(
                selected_model_title
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=500,
                detail="Could not generate book recommendations.",
            ) from exc

        recommendations = []

        for recommended_title, distance in knn_results:
            book = get_book_metadata(
                recommender,
                recommended_title,
            )
            book["distance"] = float(distance)
            recommendations.append(book)

        return {
            "extracted_text": extracted_text,
            "detections": detections,
            "matched_book": matched_book,
            "recommendations": recommendations,
            "count": len(recommendations),
            "message": "Book found and recommendations generated.",
        }

    finally:
        file.file.close()
