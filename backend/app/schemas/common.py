from pydantic import BaseModel


class PageResult[T](BaseModel):
    items: list[T]
    total: int
    page: int
    page_size: int
