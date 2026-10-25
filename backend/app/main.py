
from contextlib import asynccontextmanager
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from app.db.mongodb import check_mongodb_connection
from app.db.mongodb import (
    check_mongodb_connection,
    close_mongodb_connection,
    db,
    ensure_indexes,
)
from app.ml.recommender import BookRecommender
from app.api.routes.auth import router as auth_router
from app.api.routes.library import router as library_router
from app.api.routes.image_search import router as image_search_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.command("ping")
    ensure_indexes()
    app.state.recommender = BookRecommender()

    yield

    close_mongodb_connection()


app = FastAPI(
    title="BookWise API",
    description="Book discovery and KNN recommendations",
    version="1.0.0",
    lifespan=lifespan,
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:4200",
        "http://127.0.0.1:4200",
        
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(library_router)
app.include_router(image_search_router)

@app.get("/api/health")
def health_check():
    mongo_connected = check_mongodb_connection()

    return {
        "status": "ok" if mongo_connected else "degraded",
        "mongodb": "connected" if mongo_connected else "disconnected"
    }


@app.get("/api/books/featured")
def get_featured_books(
    limit: int = Query(default=12, ge=4, le=30)
):
    recommender = app.state.recommender

    books = recommender.df_books.copy()
    available_titles = set(recommender.piv.index)

    # Keep books available in the KNN model and with an ISBN.
    books = books.dropna(subset=["title", "isbn"]).copy()
    books = books[
        books["title"].isin(available_titles)
    ].copy()

    # Prefer one entry per title.
    books = books.drop_duplicates(subset=["title"])

    # A stable selection, so books don't change on every request.
    books = books.sort_values("title").head(limit)

    results = []

    for _, row in books.iterrows():
        author = row.get("author", "")
        isbn = row.get("isbn", "")

        results.append({
            "title": str(row["title"]),
            "author": str(author) if pd.notna(author) else "Unknown",
            "isbn": str(isbn).strip(),
        })

    return {
        "count": len(results),
        "results": results,
    }

@app.get("/api/books/search")
def search_books(
    q: str = Query(min_length=1, max_length=150),
    limit: int = Query(default=10, ge=1, le=50),
):
    recommender = app.state.recommender

    books = recommender.df_books

    query = q.strip()

    if not query:
        raise HTTPException(
            status_code=422,
            detail="Search query cannot be empty.",
        )

    title_match = books["title"].str.contains(
        query, case=False, regex=False, na=False
    )

    author_match = books["author"].str.contains(
        query, case=False, regex=False, na=False
    )

    available_titles = set(recommender.piv.index)

    results = books[
        (title_match | author_match)
        & books["title"].isin(available_titles)
    ].copy()

    results = results.drop_duplicates(subset=["isbn"])
    results = results.head(limit)

    return {
        "query": query,
        "count": len(results),
        "results": [
            {
                "isbn": row["isbn"],
                "title": row["title"],
                "author": (
                    row["author"]
                    if row["author"] and row["author"] != "nan"
                    else "Unknown"
                ),
            }
            for _, row in results.iterrows()
        ],
    }



@app.get("/api/recommendations")
def get_recommendations(
    title: str = Query(min_length=1, max_length=300)
):
    recommender = app.state.recommender
    title = title.strip()

    if not title:
        raise HTTPException(
            status_code=422,
            detail="Book title cannot be empty."
        )

    try:
        original_title, recommendations = (
            recommender.get_recommends(title)
        )
    except ValueError:
        raise HTTPException(
            status_code=404,
            detail=(
                "Book not found in the recommendation model. "
                "Try a title available in the filtered dataset."
            )
        )

    books = recommender.df_books

    metadata = (
        books.dropna(subset=["title"])
        .drop_duplicates(subset=["title"])
        .set_index("title")
    )

    results = []

    for recommended_title, distance in recommendations:
        isbn = ""
        author = "Unknown"

        if recommended_title in metadata.index:
            row = metadata.loc[recommended_title]

            isbn_value = row["isbn"]
            author_value = row["author"]

            if pd.notna(isbn_value):
                isbn = str(isbn_value)

            if pd.notna(author_value):
                author = str(author_value)

        results.append({
            "title": recommended_title,
            "author": author,
            "isbn": isbn,
            "distance": distance
        })

    return {
        "book": original_title,
        "count": len(results),
        "recommendations": results
    }

@app.get("/api/database/status")
def database_status():
    try:
        db.command("ping")
        return {
            "status": "ok",
            "database": "bookwise",
            "mongodb": "connected",
        }
    except Exception:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=503,
            detail="MongoDB is unavailable",
        )
