"""SQLAlchemy models.

Importing this package registers every table on `Base.metadata`, which is what
Alembic autogenerate reads.
"""

from app.db.base import Base
from app.models.agent_run import AgentRun
from app.models.approval import ApprovalDecision
from app.models.asset import Asset
from app.models.audit import AuditEvent
from app.models.diagnosis import Diagnosis, DiagnosisAlternative, EvidenceItem
from app.models.enums import (
    ActorType,
    AgentKind,
    AgentRunStatus,
    ApprovalDecisionType,
    AssetStatus,
    ConfidenceBand,
    Criticality,
    EvidenceType,
    PartCheckStatus,
    ProductionImpact,
    ProposalStatus,
    RecommendedAction,
    ScenarioType,
    Severity,
    WorkflowStatus,
    WorkOrderStatus,
    pg_enum,
)
from app.models.incident import Incident
from app.models.maintenance import MaintenanceProposal, PartCheck
from app.models.sentinel import SentinelAnomaly
from app.models.work_order import TechnicianOutcome, WorkOrder

__all__ = [
    "ActorType",
    "AgentKind",
    "AgentRun",
    "AgentRunStatus",
    "ApprovalDecision",
    "ApprovalDecisionType",
    "Asset",
    "AssetStatus",
    "AuditEvent",
    "Base",
    "ConfidenceBand",
    "Criticality",
    "Diagnosis",
    "DiagnosisAlternative",
    "EvidenceItem",
    "EvidenceType",
    "Incident",
    "MaintenanceProposal",
    "PartCheck",
    "PartCheckStatus",
    "ProductionImpact",
    "ProposalStatus",
    "RecommendedAction",
    "ScenarioType",
    "SentinelAnomaly",
    "Severity",
    "TechnicianOutcome",
    "WorkOrder",
    "WorkOrderStatus",
    "WorkflowStatus",
    "pg_enum",
]
