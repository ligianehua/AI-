from typing import Any, cast

from pydantic import BaseModel, model_validator


class PageResult[T](BaseModel):
    items: list[T]
    total: int
    page: int
    page_size: int


def forbid_explicit_null(*field_names: str) -> Any:
    """Update schema 用：`T | None = None` 的"未提供"与"显式 null"同型，
    对底层 NOT NULL 列显式传 null 会绕过校验并在 commit 时炸 500——在此拦成 422。
    用法：类体内 `_no_null = forbid_explicit_null("name", "status")`
    """

    def _check(_cls: type, values: Any) -> Any:
        if isinstance(values, dict):
            for field in field_names:
                if field in values and values[field] is None:
                    raise ValueError(f"字段 {field} 不能为 null")
        return values

    # classmethod 包装是 pydantic 对类体内复用 validator 的运行时要求，类型层面直接 cast
    return model_validator(mode="before")(cast(Any, classmethod(_check)))
