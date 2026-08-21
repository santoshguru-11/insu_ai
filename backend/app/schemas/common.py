"""Shared Pydantic building blocks."""

from __future__ import annotations

from typing import Any

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
