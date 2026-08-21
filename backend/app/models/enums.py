"""Domain enumerations.

Stored as native PostgreSQL enum types so invalid values are rejected by the
database, not just by the application.
"""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy import Enum as SAEnum


class Criticality(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AssetStatus(StrEnum):
    OPERATIONAL = "operational"
    DEGRADED = "degraded"
    DOWN = "down"
    MAINTENANCE = "maintenance"
    DECOMMISSIONED = "decommissioned"


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    MAJOR = "major"
    CRITICAL = "critical"


class WorkflowStatus(StrEnum):
    """Where an incident sits in the detect -> diagnose -> approve -> repair flow."""

    DETECTED = "detected"
    DIAGNOSING = "diagnosing"
    DIAGNOSED = "diagnosed"
    PROPOSED = "proposed"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CANCELLED = "cancelled"


class AgentRunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"


class EvidenceType(StrEnum):
    SENSOR_READING = "sensor_reading"
    SPECTRAL_FEATURE = "spectral_feature"
    THRESHOLD_BREACH = "threshold_breach"
    TREND = "trend"
    MAINTENANCE_HISTORY = "maintenance_history"
    MANUAL_OBSERVATION = "manual_observation"


class ProposalStatus(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    CANCELLED = "cancelled"


class ProductionImpact(StrEnum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    LINE_STOP = "line_stop"


class PartCheckStatus(StrEnum):
    PENDING = "pending"
    AVAILABLE = "available"
    BACKORDERED = "backordered"
    UNAVAILABLE = "unavailable"
    RESERVED = "reserved"


class ApprovalDecisionType(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class WorkOrderStatus(StrEnum):
    DRAFT = "draft"
    OPEN = "open"
    DISPATCHED = "dispatched"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ActorType(StrEnum):
    HUMAN = "human"
    AGENT = "agent"
    SYSTEM = "system"
    EXTERNAL_SYSTEM = "external_system"


def pg_enum(enum_cls: type[StrEnum], name: str) -> SAEnum:
    """A native PostgreSQL enum type whose labels are the enum *values*.

    SQLAlchemy defaults to storing member *names* (`LINE_STOP`); using the
    values keeps what is in the database identical to what the API emits.
    """
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=True,
        validate_strings=True,
        values_callable=lambda enum: [member.value for member in enum],
    )
