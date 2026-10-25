
from app.ml.recommender import BookRecommender


def test_book_recommendation():
    recommender = BookRecommender()

    book_title = (
        "Where the Heart Is (Oprah's Book Club (Paperback))"
    )

    recommends = recommender.get_recommends(book_title)

    print("\nOriginal book:")
    print(recommends[0])

    print("\nRecommended books:")

    for title, distance in recommends[1]:
        print(f"{title} | distance = {distance:.4f}")

    assert recommends[0] == book_title
    assert isinstance(recommends[1], list)

    assert all(
        title != book_title
        for title, distance in recommends[1]
    )

    assert len(recommends[1]) <= 5

    print("\nBasic tests passed!")


if __name__ == "__main__":
    test_book_recommendation()
