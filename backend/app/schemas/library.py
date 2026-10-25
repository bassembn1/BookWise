
from pydantic import BaseModel, Field


class AddBookRequest(BaseModel):
    isbn: str = Field(min_length=10, max_length=13)
    title: str = Field(min_length=1, max_length=300)
    author: str = Field(default="Unknown", max_length=200)


class LibraryBookResponse(BaseModel):
    isbn: str
    title: str
    author: str
    added_at: str
