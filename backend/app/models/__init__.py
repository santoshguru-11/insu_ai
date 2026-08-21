"""SQLAlchemy models.

Importing this package registers every table on `Base.metadata`, which is what
Alembic autogenerate reads.
"""

from app.db.base import Base
from app.models.agent_run import AgentRun
from app.models.approval import ApprovalDecision
from app.models.asset import Asset
from app.models.audit import AuditEvent
from app.models.diagnosis import Diagnosis, EvidenceItem
from app.models.enums import (
    ActorType,
    AgentRunStatus,
    ApprovalDecisionType,
    AssetStatus,
    Criticality,
    EvidenceType,
    PartCheckStatus,
    ProductionImpact,
    ProposalStatus,
    Severity,
    WorkflowStatus,
    WorkOrderStatus,
    pg_enum,
)
from app.models.incident import Incident
from app.models.maintenance import MaintenanceProposal, PartCheck
from app.models.work_order import TechnicianOutcome, WorkOrder

__all__ = [
    "ActorType",
    "AgentRun",
    "AgentRunStatus",
    "ApprovalDecision",
    "ApprovalDecisionType",
    "Asset",
    "AssetStatus",
    "AuditEvent",
    "Base",
    "Criticality",
    "Diagnosis",
    "EvidenceItem",
    "EvidenceType",
    "Incident",
    "MaintenanceProposal",
    "PartCheck",
    "PartCheckStatus",
    "ProductionImpact",
    "ProposalStatus",
    "Severity",
    "TechnicianOutcome",
    "WorkOrder",
    "WorkOrderStatus",
    "WorkflowStatus",
    "pg_enum",
]
