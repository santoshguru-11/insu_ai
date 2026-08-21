"""Assembles ORM rows into the API's incident contracts.

Kept out of the routers so the same detail payload can be reused by the REST
response, the WebSocket snapshot, and the transition broadcasts.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.diagnosis import Diagnosis
from app.models.incident import Incident
from app.models.maintenance import MaintenanceProposal
from app.models.work_order import WorkOrder
from app.repositories.incident import IncidentRepository
from app.schemas.approval import ApprovalDecisionRead
from app.schemas.asset import AssetRead
from app.schemas.diagnosis import (
    AgentRunRead,
    DiagnosisAlternativeRead,
    DiagnosisRead,
    DiagnosisSummary,
    EvidenceItemRead,
    RULEstimate,
    SentinelAnomalyRead,
)
from app.schemas.incident import IncidentDetail, IncidentListItem
from app.schemas.maintenance import (
    MaintenanceProposalRead,
    PartCheckRead,
    TechnicianOutcomeRead,
    WorkOrderRead,
)


def rul_from_diagnosis(diagnosis: Diagnosis | None) -> RULEstimate | None:
    if diagnosis is None:
        return None
    return RULEstimate(
        estimate_days=diagnosis.rul_estimate_days,
        ci_low_days=diagnosis.rul_ci_low_days,
        ci_high_days=diagnosis.rul_ci_high_days,
    )


def _latest(rows: Sequence[object]) -> object | None:
    """Newest row by `created_at`, or None. Works on already-loaded collections."""
    if not rows:
        return None
    return max(rows, key=lambda row: row.created_at)


def build_diagnosis(diagnosis: Diagnosis) -> DiagnosisRead:
    return DiagnosisRead(
        id=diagnosis.id,
        incident_id=diagnosis.incident_id,
        agent_run_id=diagnosis.agent_run_id,
        failure_mode_code=diagnosis.failure_mode_code,
        fmea_reference=diagnosis.fmea_reference,
        confidence=diagnosis.confidence,
        confidence_band=diagnosis.confidence_band,
        recommended_action=diagnosis.recommended_action,
        recommended_action_note=diagnosis.recommended_action_note,
        similar_work_order_reference=diagnosis.similar_work_order_reference,
        rul=rul_from_diagnosis(diagnosis) or RULEstimate(),
        alternatives=[
            DiagnosisAlternativeRead.model_validate(alternative)
            for alternative in sorted(
                diagnosis.alternatives, key=lambda a: (-(a.confidence or 0), a.failure_mode_code)
            )
        ],
        evidence_items=[
            EvidenceItemRead.model_validate(item)
            for item in sorted(diagnosis.evidence_items, key=lambda e: e.created_at)
        ],
        created_at=diagnosis.created_at,
        updated_at=diagnosis.updated_at,
    )


def build_proposal(proposal: MaintenanceProposal) -> MaintenanceProposalRead:
    return MaintenanceProposalRead(
        id=proposal.id,
        incident_id=proposal.incident_id,
        proposed_start_at=proposal.proposed_start_at,
        proposed_end_at=proposal.proposed_end_at,
        duration_hours=proposal.duration_hours,
        rul_margin_days=proposal.rul_margin_days,
        production_impact=proposal.production_impact,
        crew_available=proposal.crew_available,
        planned_changeover=proposal.planned_changeover,
        status=proposal.status,
        part_checks=[
            PartCheckRead.model_validate(check)
            for check in sorted(proposal.part_checks, key=lambda c: c.sku)
        ],
        created_at=proposal.created_at,
        updated_at=proposal.updated_at,
    )


def build_detail(incident: Incident) -> IncidentDetail:
    """Build the full detail payload from an incident loaded with `get_with_detail`."""
    diagnosis: Diagnosis | None = _latest(incident.diagnoses)  # type: ignore[assignment]
    proposal: MaintenanceProposal | None = _latest(incident.maintenance_proposals)  # type: ignore[assignment]
    approval = _latest(incident.approval_decisions)
    work_order: WorkOrder | None = _latest(incident.work_orders)  # type: ignore[assignment]
    outcome = _latest(work_order.technician_outcomes) if work_order else None

    return IncidentDetail(
        id=incident.id,
        trace_id=incident.trace_id,
        workflow_status=incident.workflow_status,
        severity=incident.severity,
        scenario_type=incident.scenario_type,
        cloud_available=incident.cloud_available,
        human_review_reason=incident.human_review_reason,
        detected_at=incident.detected_at,
        resolved_at=incident.resolved_at,
        created_at=incident.created_at,
        updated_at=incident.updated_at,
        asset=AssetRead.model_validate(incident.asset),
        anomalies=[
            SentinelAnomalyRead.model_validate(anomaly)
            for anomaly in sorted(incident.sentinel_anomalies, key=lambda a: a.detected_at)
        ],
        agent_runs=[
            AgentRunRead.model_validate(run)
            for run in sorted(incident.agent_runs, key=lambda r: r.created_at)
        ],
        diagnosis=build_diagnosis(diagnosis) if diagnosis else None,
        rul=rul_from_diagnosis(diagnosis),
        proposal=build_proposal(proposal) if proposal else None,
        approval=ApprovalDecisionRead.model_validate(approval) if approval else None,
        work_order=WorkOrderRead.model_validate(work_order) if work_order else None,
        technician_outcome=TechnicianOutcomeRead.model_validate(outcome) if outcome else None,
    )


def build_list_item(incident: Incident) -> IncidentListItem:
    """Build one list row from an incident loaded with its asset and diagnoses."""
    diagnosis: Diagnosis | None = _latest(incident.diagnoses)  # type: ignore[assignment]
    return IncidentListItem(
        id=incident.id,
        trace_id=incident.trace_id,
        asset_id=incident.asset_id,
        asset_name=incident.asset.name,
        asset_code=incident.asset.asset_code,
        workflow_status=incident.workflow_status,
        severity=incident.severity,
        scenario_type=incident.scenario_type,
        cloud_available=incident.cloud_available,
        diagnosis=(
            DiagnosisSummary(
                failure_mode_code=diagnosis.failure_mode_code,
                confidence=diagnosis.confidence,
                confidence_band=diagnosis.confidence_band,
                recommended_action=diagnosis.recommended_action,
                fmea_reference=diagnosis.fmea_reference,
            )
            if diagnosis
            else None
        ),
        rul=rul_from_diagnosis(diagnosis),
        detected_at=incident.detected_at,
        resolved_at=incident.resolved_at,
        updated_at=incident.updated_at,
    )


class IncidentViewService:
    """Loads an incident and renders it as the API contract."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = IncidentRepository(session)

    async def require(self, incident_id: uuid.UUID) -> Incident:
        incident = await self.repository.get(incident_id)
        if incident is None:
            raise NotFoundError(
                f"No incident with id {incident_id}.",
                details={"incident_id": str(incident_id)},
            )
        return incident

    async def detail(self, incident_id: uuid.UUID) -> IncidentDetail:
        """Re-read the incident with every relationship loaded, then render it."""
        # Expire first so a detail built right after a write sees the new rows.
        self.session.expire_all()
        incident = await self.repository.get_with_detail(incident_id)
        if incident is None:
            raise NotFoundError(
                f"No incident with id {incident_id}.",
                details={"incident_id": str(incident_id)},
            )
        return build_detail(incident)
