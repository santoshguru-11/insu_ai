"""Approval gate contracts.

The approval token is the mechanism that makes irreversible downstream work
(part reservation, work-order creation) traceable to a specific human decision.
Only the token's id and hash are persisted; the raw token is returned exactly
once, on the response that creates it.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import ApprovalDecisionType
from app.schemas.common import ORMModel


class ApprovalRequest(BaseModel):
    """Body for both the approve and reject endpoints."""

    approver_id: str = Field(max_length=128, examples=["user-id"])
    approver_name: str = Field(max_length=255, examples=["A. Iyer"])
    reason: str | None = Field(
        default=None,
        max_length=2000,
        examples=["Approved during scheduled changeover"],
    )


class ApprovalTokenRead(BaseModel):
    """Token metadata. The raw secret is never included here."""

    token_id: uuid.UUID
    expires_at: datetime
    scope: str = Field(
        description="What the token authorises, as `incident:<id>:<action>`.",
        examples=["incident:0f1a.../approve"],
    )


class ApprovalDecisionRead(ORMModel):
    id: uuid.UUID
    incident_id: uuid.UUID
    proposal_id: uuid.UUID
    decision: ApprovalDecisionType
    approver_id: str | None = None
    approver_name: str | None = None
    reason: str | None = None
    token_id: uuid.UUID | None = None
    token_expires_at: datetime | None = None
    used_at: datetime | None = None
    decided_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
