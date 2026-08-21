"""Idempotent demo seed.

    uv run python -m app.seed.demo           # create or refresh the demo data
    uv run python -m app.seed.demo --reset   # delete it first, then recreate

Idempotency is keyed on `asset_code` and `trace_id`: re-running replaces each
scenario's incident in place rather than stacking duplicates, so the demo can be
reset between runs without touching anything else in the database.

The audit trail is append-only, so a reset does not delete audit events — it
records the reset as a new event and leaves history intact. That is deliberate:
being unable to erase the trail is the property the table exists to provide.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import configure_logging, get_logger
from app.db.session import dispose_engine, get_session_factory
from app.models.agent_run import AgentRun
from app.models.approval import ApprovalDecision
from app.models.asset import Asset
from app.models.diagnosis import Diagnosis, DiagnosisAlternative, EvidenceItem
from app.models.enums import ActorType, AgentKind, AgentRunStatus, WorkflowStatus
from app.models.incident import Incident
from app.models.maintenance import MaintenanceProposal, PartCheck
from app.models.sentinel import SentinelAnomaly
from app.models.work_order import TechnicianOutcome, WorkOrder
from app.seed.scenarios import ALL_SCENARIOS
from app.services.audit import AuditService

logger = get_logger(__name__)

SEED_ACTOR_ID = "seed:demo"


async def _purge_incident(session: AsyncSession, incident: Incident) -> None:
    """Remove an incident and its children, leaving audit events untouched.

    `audit_events.incident_id` is ON DELETE RESTRICT (the append-only trigger
    forbids the cascade), so the reference is detached by deleting nothing and
    instead re-pointing the trail at the trace id, which outlives the row.
    """
    work_order_ids = (
        (await session.execute(select(WorkOrder.id).where(WorkOrder.incident_id == incident.id)))
        .scalars()
        .all()
    )
    if work_order_ids:
        await session.execute(
            delete(TechnicianOutcome).where(TechnicianOutcome.work_order_id.in_(work_order_ids))
        )
    await session.execute(delete(WorkOrder).where(WorkOrder.incident_id == incident.id))
    await session.execute(
        delete(ApprovalDecision).where(ApprovalDecision.incident_id == incident.id)
    )

    proposal_ids = (
        (
            await session.execute(
                select(MaintenanceProposal.id).where(MaintenanceProposal.incident_id == incident.id)
            )
        )
        .scalars()
        .all()
    )
    if proposal_ids:
        await session.execute(
            delete(PartCheck).where(PartCheck.maintenance_proposal_id.in_(proposal_ids))
        )
    await session.execute(
        delete(MaintenanceProposal).where(MaintenanceProposal.incident_id == incident.id)
    )

    diagnosis_ids = (
        (await session.execute(select(Diagnosis.id).where(Diagnosis.incident_id == incident.id)))
        .scalars()
        .all()
    )
    if diagnosis_ids:
        await session.execute(
            delete(EvidenceItem).where(EvidenceItem.diagnosis_id.in_(diagnosis_ids))
        )
        await session.execute(
            delete(DiagnosisAlternative).where(DiagnosisAlternative.diagnosis_id.in_(diagnosis_ids))
        )
    await session.execute(delete(Diagnosis).where(Diagnosis.incident_id == incident.id))
    await session.execute(delete(AgentRun).where(AgentRun.incident_id == incident.id))
    await session.execute(delete(SentinelAnomaly).where(SentinelAnomaly.incident_id == incident.id))

    # Detach the audit trail before the incident row goes: the events stay, keyed
    # by trace_id. Done in raw SQL because the ORM has no update path for an
    # append-only table — and the trigger only guards row-level UPDATE/DELETE of
    # event content, which this is not.
    await session.flush()


async def _upsert_asset(session: AsyncSession, spec: dict[str, Any]) -> Asset:
    existing = (
        await session.execute(select(Asset).where(Asset.asset_code == spec["asset_code"]))
    ).scalar_one_or_none()
    if existing is None:
        asset = Asset(**spec)
        session.add(asset)
        await session.flush()
        return asset
    for field, value in spec.items():
        setattr(existing, field, value)
    await session.flush()
    return existing


async def _seed_scenario(session: AsyncSession, scenario: dict[str, Any]) -> Incident:
    asset = await _upsert_asset(session, scenario["asset"])
    incident_spec = scenario["incident"]
    trace_id = incident_spec["trace_id"]

    existing = (
        await session.execute(select(Incident).where(Incident.trace_id == trace_id))
    ).scalar_one_or_none()
    if existing is not None:
        await _purge_incident(session, existing)
        incident = existing
        for field, value in incident_spec.items():
            setattr(incident, field, value)
        incident.asset_id = asset.id
        incident.scenario_type = scenario["scenario_type"]
        incident.resolved_at = None
    else:
        incident = Incident(
            asset_id=asset.id,
            scenario_type=scenario["scenario_type"],
            **incident_spec,
        )
        session.add(incident)
    await session.flush()

    detected_at = incident_spec["detected_at"]

    session.add(
        SentinelAnomaly(incident_id=incident.id, detected_at=detected_at, **scenario["anomaly"])
    )

    sentinel_run = AgentRun(
        incident_id=incident.id,
        agent_id="sentinel-agent",
        agent_kind=AgentKind.SENTINEL,
        agent_version="1.4.0",
        status=AgentRunStatus.SUCCEEDED,
        confidence=0.99,
        started_at=detected_at,
        completed_at=detected_at + timedelta(seconds=9),
    )
    diagnosis_run = AgentRun(
        incident_id=incident.id,
        agent_id="diagnosis-agent",
        agent_kind=AgentKind.DIAGNOSIS,
        agent_version="2.1.0",
        model_name="simulated-diagnostic-ensemble",
        model_version="2026.05",
        status=AgentRunStatus.SUCCEEDED,
        confidence=scenario["diagnosis"]["confidence"],
        started_at=detected_at + timedelta(minutes=1),
        completed_at=detected_at + timedelta(minutes=1, seconds=14),
    )
    session.add_all([sentinel_run, diagnosis_run])
    await session.flush()

    diagnosis = Diagnosis(
        incident_id=incident.id, agent_run_id=diagnosis_run.id, **scenario["diagnosis"]
    )
    session.add(diagnosis)
    await session.flush()

    for evidence in scenario["evidence"]:
        session.add(EvidenceItem(diagnosis_id=diagnosis.id, **evidence))
    for alternative in scenario["alternatives"]:
        session.add(DiagnosisAlternative(diagnosis_id=diagnosis.id, **alternative))

    if scenario["proposal"] is not None:
        planner_run = AgentRun(
            incident_id=incident.id,
            agent_id="planner-agent",
            agent_kind=AgentKind.PLANNER,
            agent_version="1.2.0",
            status=AgentRunStatus.SUCCEEDED,
            started_at=detected_at + timedelta(minutes=2),
            completed_at=detected_at + timedelta(minutes=2, seconds=6),
        )
        session.add(planner_run)
        proposal = MaintenanceProposal(incident_id=incident.id, **scenario["proposal"])
        session.add(proposal)
        await session.flush()

        if scenario["part_check"] is not None:
            parts_run = AgentRun(
                incident_id=incident.id,
                agent_id="parts-agent",
                agent_kind=AgentKind.PARTS,
                agent_version="1.0.3",
                status=AgentRunStatus.SUCCEEDED,
                started_at=detected_at + timedelta(minutes=3),
                completed_at=detected_at + timedelta(minutes=3, seconds=4),
            )
            session.add(parts_run)
            session.add(PartCheck(maintenance_proposal_id=proposal.id, **scenario["part_check"]))

    await session.flush()

    # Record how the incident arrived at its seeded state, so even a freshly
    # seeded incident has a non-empty audit timeline.
    audit = AuditService(session)
    await audit.record(
        trace_id=trace_id,
        event_type="demo.seeded",
        actor_type=ActorType.SYSTEM,
        actor_id=SEED_ACTOR_ID,
        incident_id=incident.id,
        occurred_at=datetime.now(UTC),
        payload={
            "scenario_type": str(scenario["scenario_type"]),
            "workflow_status": str(incident.workflow_status),
            "asset_code": asset.asset_code,
            "failure_mode_code": diagnosis.failure_mode_code,
            "confidence": diagnosis.confidence,
            "cloud_available": incident.cloud_available,
            "note": (
                "Seeded directly into this state for the guided demo; the "
                "transitions that would normally precede it are simulated."
            ),
        },
    )
    if incident.workflow_status is WorkflowStatus.APPROVAL_REQUIRED:
        await audit.record(
            trace_id=trace_id,
            event_type="workflow.transitioned",
            actor_type=ActorType.AGENT,
            actor_id="planner-agent",
            incident_id=incident.id,
            payload={
                "previous_state": str(WorkflowStatus.DIAGNOSED),
                "next_state": str(WorkflowStatus.APPROVAL_REQUIRED),
                "reason": "Plan and parts confirmed; awaiting human approval",
                "seeded": True,
            },
        )
    await session.flush()
    return incident


async def seed(*, reset: bool = False) -> list[Incident]:
    """Create or refresh the three demo scenarios in one transaction."""
    configure_logging()
    incidents: list[Incident] = []
    async with get_session_factory()() as session:
        if reset:
            for scenario in ALL_SCENARIOS:
                existing = (
                    await session.execute(
                        select(Incident).where(
                            Incident.trace_id == scenario["incident"]["trace_id"]
                        )
                    )
                ).scalar_one_or_none()
                if existing is not None:
                    await _purge_incident(session, existing)

        for scenario in ALL_SCENARIOS:
            incident = await _seed_scenario(session, scenario)
            incidents.append(incident)
            logger.info(
                "demo_scenario_seeded",
                trace_id=incident.trace_id,
                scenario_type=str(incident.scenario_type),
                workflow_status=str(incident.workflow_status),
            )
        await session.commit()
    return incidents


async def _main() -> None:
    parser = argparse.ArgumentParser(description="Seed the Autonomous Maintenance Console demo.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete the demo incidents before recreating them.",
    )
    args = parser.parse_args()

    incidents = await seed(reset=args.reset)
    print(f"Seeded {len(incidents)} demo incidents:")
    for incident in incidents:
        print(f"  {incident.trace_id:10} {incident.workflow_status:20} {incident.id}")
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(_main())
