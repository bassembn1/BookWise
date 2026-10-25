
from pathlib import Path

import pandas as pd
from scipy.sparse import csr_matrix
from sklearn.neighbors import NearestNeighbors


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data" / "raw"

BOOKS_FILE = DATA_DIR / "BX-Books.csv"
RATINGS_FILE = DATA_DIR / "BX-Book-Ratings.csv"


class BookRecommender:
    def __init__(self):

        if not BOOKS_FILE.exists():
            raise FileNotFoundError(
                f"Books file not found: {BOOKS_FILE}"
            )

        if not RATINGS_FILE.exists():
            raise FileNotFoundError(
                f"Ratings file not found: {RATINGS_FILE}"
            )


        self.df_books = pd.read_csv(
            BOOKS_FILE,
            encoding="ISO-8859-1",
            sep=";",
            header=0,
            names=["isbn", "title", "author"],
            usecols=["isbn", "title", "author"],
            dtype={
                "isbn": str,
                "title": str,
                "author": str
            },
            on_bad_lines="skip"
        )

        self.df_ratings = pd.read_csv(
            RATINGS_FILE,
            encoding="ISO-8859-1",
            sep=";",
            header=0,
            names=["user", "isbn", "rating"],
            usecols=["user", "isbn", "rating"],
            dtype={
                "user": "int32",
                "isbn": str,
                "rating": "float32"
            },
            on_bad_lines="skip"
        )


        self.df_books = self.df_books.dropna(
            subset=["isbn", "title"]
        )

        self.df_ratings = self.df_ratings.dropna(
            subset=["user", "isbn", "rating"]
        )

        self.df_ratings = self.df_ratings[
            self.df_ratings["rating"].between(0, 10)
        ]


        counts_users = self.df_ratings["user"].value_counts()
        counts_books = self.df_ratings["isbn"].value_counts()

        self.df_ratings = self.df_ratings[
            self.df_ratings["user"].isin(
                counts_users[counts_users >= 200].index
            )
        ]

        self.df_ratings = self.df_ratings[
            self.df_ratings["isbn"].isin(
                counts_books[counts_books >= 100].index
            )
        ]


        df = pd.merge(
            self.df_books,
            self.df_ratings,
            on="isbn",
            how="inner"
        )

        df = df.drop_duplicates(
            subset=["title", "user"]
        )


        self.piv = df.pivot(
            index="title",
            columns="user",
            values="rating"
        ).fillna(0)


        self.matrix = csr_matrix(
            self.piv.to_numpy()
        )



        self.model_knn = NearestNeighbors(
            metric="cosine",
            algorithm="brute"
        )

        self.model_knn.fit(self.matrix)

        print("BookWise KNN engine initialized successfully.")
        print(f"Books in model: {self.matrix.shape[0]:,}")
        print(f"Users in model: {self.matrix.shape[1]:,}")


    def get_recommends(self, book=""):

        if book not in self.piv.index:
            raise ValueError(
                f"Book not found in recommendation model: {book}"
            )

        book_index = self.piv.index.get_loc(book)

        book_vector = self.matrix[book_index]

        n_neighbors = min(6, self.matrix.shape[0])

        distances, indices = self.model_knn.kneighbors(
            book_vector,
            n_neighbors=n_neighbors
        )

        recommendations = []

        for distance, index in zip(
            distances[0],
            indices[0]
        ):
            recommended_title = self.piv.index[index]

            if distance != 0:
                recommendations.append([
                    recommended_title,
                    float(distance)
                ])

        recommendations = recommendations[::-1]

        return [book, recommendations]
