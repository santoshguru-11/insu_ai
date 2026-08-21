"""Shared Pydantic building blocks."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    """Base for response models read straight off SQLAlchemy instances."""

    model_config = ConfigDict(from_attributes=True)


class ErrorDetail(BaseModel):
    code: str = Field(examples=["NOT_FOUND"])
    message: str = Field(examples=["The requested resource was not found."])
    request_id: str = Field(examples=["6f1a4f3e-6a1b-4a0a-9a1e-2a9b7f0d1c33"])
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    """The single error envelope every failing request returns."""

    error: ErrorDetail


Limit = Annotated[int, Field(ge=1, le=200, description="Maximum rows to return.")]
Offset = Annotated[int, Field(ge=0, description="Rows to skip before returning results.")]


class Page[ItemT](BaseModel):
    """Offset/limit page envelope used by every list endpoint."""

    items: list[ItemT]
    total: int = Field(description="Total rows matching the filters, ignoring paging.")
    limit: int
    offset: int

    @property
    def has_more(self) -> bool:
        return self.offset + len(self.items) < self.total
