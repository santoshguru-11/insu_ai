"""Asset request/response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import AssetStatus, Criticality
from app.schemas.common import ORMModel


class AssetBase(BaseModel):
    asset_code: str = Field(max_length=64, examples=["CAL-04-DRIVE"])
    name: str = Field(max_length=255, examples=["Calender line 4 main drive"])
    plant_name: str = Field(max_length=255, examples=["Hanover Plant"])
    line_name: str = Field(max_length=255, examples=["Calender Line 4"])
    criticality: Criticality = Criticality.MEDIUM
    status: AssetStatus = AssetStatus.OPERATIONAL


class AssetCreate(AssetBase):
    pass


class AssetUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    plant_name: str | None = Field(default=None, max_length=255)
    line_name: str | None = Field(default=None, max_length=255)
    criticality: Criticality | None = None
    status: AssetStatus | None = None


class AssetRead(ORMModel, AssetBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
