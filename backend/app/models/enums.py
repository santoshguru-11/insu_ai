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
    """ISO 20816-3 vibration evaluation zones.

    The product grades every anomaly on the ISO scale rather than a generic
    info/warning ladder, so the value carries an engineering meaning:
    A = new-machine condition, B = acceptable long term,
    C = unsatisfactory for continuous operation, D = damage likely.
    """

    ISO_20816_3_BAND_A = "iso_20816_3_band_a"
    ISO_20816_3_BAND_B = "iso_20816_3_band_b"
    ISO_20816_3_BAND_C = "iso_20816_3_band_c"
    ISO_20816_3_BAND_D = "iso_20816_3_band_d"


class WorkflowStatus(StrEnum):
    """Where an incident sits in the sentinel -> diagnose -> approve -> repair flow.

    The legal moves between these states live in
    `app.services.workflow.ALLOWED_TRANSITIONS`; nothing else may change an
    incident's state.
    """

    WATCH = "watch"
    ESCALATED = "escalated"
    DIAGNOSED = "diagnosed"
    HUMAN_REVIEW = "human_review"
    APPROVAL_REQUIRED = "approval_required"
    APPROVED = "approved"
    REJECTED = "rejected"
    WORK_ORDER_LIVE = "work_order_live"
    RESOLVED = "resolved"


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
    PROPOSED = "proposed"
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
    # Availability confirmed but nothing held: the state a part check sits in
    # until an approval authorises the (irreversible) reservation.
    CHECKED_NOT_RESERVED = "checked_not_reserved"
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


class ScenarioType(StrEnum):
    """Which demo storyline an incident belongs to."""

    NORMAL = "normal"
    LOW_CONFIDENCE = "low_confidence"
    OFFLINE = "offline"


class ConfidenceBand(StrEnum):
    """Banded view of a numeric confidence score, used by the transition rules."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

    @classmethod
    def from_score(cls, score: float) -> ConfidenceBand:
        if score < LOW_CONFIDENCE_CEILING:
            return cls.LOW
        if score < MEDIUM_CONFIDENCE_CEILING:
            return cls.MEDIUM
        return cls.HIGH


# A diagnosis below this score is not trusted enough to ask a human to approve
# work; it goes to human_review instead.
LOW_CONFIDENCE_CEILING = 0.60
MEDIUM_CONFIDENCE_CEILING = 0.85


class RecommendedAction(StrEnum):
    """What the diagnosis agent recommends doing about the failure mode."""

    MONITOR = "monitor"
    SCHEDULE_INSPECTION = "schedule_inspection"
    SCHEDULE_ALIGNMENT = "schedule_alignment"
    SCHEDULE_REPLACEMENT = "schedule_replacement"
    IMMEDIATE_STOP = "immediate_stop"


class AgentKind(StrEnum):
    """The simulated agents that act on an incident, in pipeline order."""

    SENTINEL = "sentinel"
    DIAGNOSIS = "diagnosis"
    PLANNER = "planner"
    PARTS = "parts"


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
