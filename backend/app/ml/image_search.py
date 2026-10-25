
import csv
import re
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path
from threading import Lock

import easyocr
import numpy as np
from PIL import Image, UnidentifiedImageError


# Project root:
# BookWise/backend/app/ml/image_search.py
PROJECT_ROOT = Path(__file__).resolve().parents[3]
BOOKS_CSV = PROJECT_ROOT / "data" / "raw" / "BX-Books.csv"

MAX_IMAGE_PIXELS = 20_000_000

_reader = None
_reader_lock = Lock()

reader = easyocr.Reader(['en'], gpu=False)
""" def get_ocr_reader():
    #Load EasyOCR only once, using the CPU.
    global _reader

    if _reader is None:
        with _reader_lock:
            if _reader is None:
                _reader = easyocr.Reader(
                    ["en"],
                    gpu=False,
                    verbose=False,
                )

    return _reader
 """

def normalize_text(text: str) -> str:
    """Normalize text to improve book title matching."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


@lru_cache(maxsize=1)
def load_books() -> list[dict]:
    """
    Load the existing Book-Crossing CSV dataset.
    The expected columns include ISBN, Book-Title and Book-Author.
    """
    if not BOOKS_CSV.exists():
        raise FileNotFoundError(
            f"Books dataset not found: {BOOKS_CSV}"
        )

    books = []

    with BOOKS_CSV.open(
        "r",
        encoding="latin-1",
        newline="",
    ) as csv_file:
        reader = csv.DictReader(csv_file, delimiter=";")

        required_columns = {
            "ISBN",
            "Book-Title",
            "Book-Author",
        }

        if not reader.fieldnames or not required_columns.issubset(
            set(reader.fieldnames)
        ):
            raise ValueError(
                "BX-Books.csv does not contain the expected columns."
            )

        for row in reader:
            title = (row.get("Book-Title") or "").strip()
            author = (row.get("Book-Author") or "").strip()
            isbn = (row.get("ISBN") or "").strip()

            if not title:
                continue

            books.append({
                "isbn": isbn,
                "title": title,
                "author": author or "Unknown",
                "normalized_title": normalize_text(title),
                "normalized_author": normalize_text(author),
            })

    return books


def extract_text_from_image(image: Image.Image) -> list[dict]:
    """Extract English text and confidence scores from a book cover."""
    #reader = get_ocr_reader()

    image = image.convert("RGB")
    image_array = np.array(image)

    detections = reader.readtext(
        image_array,
        detail=1,
        paragraph=False,
    )

    results = []

    for detection in detections:
        if len(detection) < 3:
            continue

        text = str(detection[1]).strip()

        try:
            confidence = float(detection[2])
        except (TypeError, ValueError):
            confidence = 0.0

        if text:
            results.append({
                "text": text,
                "confidence": round(confidence, 4),
            })

    return results


def find_books(ocr_results: list[dict], limit: int = 10) -> list[dict]:
    """
    Rank dataset books using OCR text.
    This is fuzzy text matching, not visual cover recognition.
    """
    if not ocr_results:
        return []

    lines = [
        normalize_text(item["text"])
        for item in ocr_results
    ]
    lines = [line for line in lines if line]

    if not lines:
        return []

    # Longer OCR lines are more likely to contain a book title.
    query = " ".join(
        sorted(lines, key=len, reverse=True)[:5]
    )

    books = load_books()
    scored_books = []

    for book in books:
        title = book["normalized_title"]
        author = book["normalized_author"]

        if not title:
            continue

        # Similarity between the combined OCR text and the title.
        title_score = SequenceMatcher(
            None,
            query,
            title,
        ).ratio()

        # A title appearing as a phrase in the OCR text is strong evidence.
        if title in query or query in title:
            title_score = max(title_score, 0.85)

        # Compare each OCR line with the title. This helps when the
        # title is printed on multiple separate lines.
        line_score = max(
            (
                SequenceMatcher(None, line, title).ratio()
                for line in lines
            ),
            default=0.0,
        )

        score = max(title_score, line_score)

        # A recognized author can provide supporting evidence.
        if author and any(
            len(line) >= 4
            and (
                author in line
                or line in author
            )
            for line in lines
        ):
            score = min(1.0, score + 0.08)

        if score >= 0.30:
            scored_books.append({
                "isbn": book["isbn"],
                "title": book["title"],
                "author": book["author"],
                "match_score": round(score, 4),
            })

    scored_books.sort(
        key=lambda item: item["match_score"],
        reverse=True,
    )

    # Remove duplicate ISBNs while preserving ranking.
    unique_results = []
    seen_isbns = set()

    for book in scored_books:
        isbn = book["isbn"]

        if isbn and isbn in seen_isbns:
            continue

        if isbn:
            seen_isbns.add(isbn)

        unique_results.append(book)

        if len(unique_results) >= limit:
            break

    return unique_results
