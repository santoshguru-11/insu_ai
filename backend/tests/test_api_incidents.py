"""Incident list, filtering and detail."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.models.incident import Incident

pytestmark = pytest.mark.db


async def test_incident_list_carries_summary_fields(
    api: AsyncClient, seeded: dict[str, Incident]
) -> None:
    response = await api.get("/incidents")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3

    main = next(item for item in body["items"] if item["trace_id"] == "tr_9f21")
    assert main["asset_name"] == "Calender Roll Drive Train"
    assert main["asset_code"] == "CAL-04-DRIVE"
    assert main["workflow_status"] == "approval_required"
    assert main["severity"] == "iso_20816_3_band_c"
    assert main["diagnosis"]["failure_mode_code"] == "BRG_OUTER_RACE_WEAR"
    assert main["diagnosis"]["confidence"] == pytest.approx(0.87)
    assert main["diagnosis"]["confidence_band"] == "high"
    assert main["rul"] == {"estimate_days": 18.0, "ci_low_days": 12.0, "ci_high_days": 26.0}


@pytest.mark.parametrize(
    ("params", "expected_traces"),
    [
        ({"workflow_status": "approval_required"}, {"tr_9f21"}),
        ({"workflow_status": "human_review"}, {"tr_5c07"}),
        ({"severity": "iso_20816_3_band_c"}, {"tr_9f21", "tr_1d88"}),
        ({"scenario_type": "offline"}, {"tr_1d88"}),
        ({"scenario_type": "low_confidence"}, {"tr_5c07"}),
        ({"workflow_status": "resolved"}, set()),
    ],
)
async def test_incident_list_filters(
    api: AsyncClient,
    seeded: dict[str, Incident],
    params: dict[str, str],
    expected_traces: set[str],
) -> None:
    response = await api.get("/incidents", params=params)

    assert response.status_code == 200
    body = response.json()
    assert {item["trace_id"] for item in body["items"]} == expected_traces
    assert body["total"] == len(expected_traces)


async def test_incident_list_filters_by_asset(api: AsyncClient, main_incident: Incident) -> None:
    response = await api.get("/incidents", params={"asset_id": str(main_incident.asset_id)})

    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["trace_id"] == "tr_9f21"


async def test_incident_detail_is_complete(api: AsyncClient, main_incident: Incident) -> None:
    """Every section the console renders must be present and populated."""
    response = await api.get(f"/incidents/{main_incident.id}")

    assert response.status_code == 200
    body = response.json()

    assert body["trace_id"] == "tr_9f21"
    assert body["workflow_status"] == "approval_required"
    assert body["severity"] == "iso_20816_3_band_c"
    assert body["scenario_type"] == "normal"
    assert body["cloud_available"] is True

    assert body["asset"]["asset_code"] == "CAL-04-DRIVE"

    # Sentinel anomaly, exactly as the scenario specifies it.
    anomaly = body["anomalies"][0]
    assert anomaly["observed_value"] == pytest.approx(4.2)
    assert anomaly["baseline_value"] == pytest.approx(1.1)
    assert anomaly["unit"] == "mm/s"
    assert anomaly["sigma_deviation"] == pytest.approx(6.4)
    assert anomaly["thermal_delta_c"] == pytest.approx(14.8)
    assert anomaly["window_count"] == 6
    assert anomaly["persisted"] is True

    assert {run["agent_kind"] for run in body["agent_runs"]} == {
        "sentinel",
        "diagnosis",
        "planner",
        "parts",
    }

    diagnosis = body["diagnosis"]
    assert diagnosis["failure_mode_code"] == "BRG_OUTER_RACE_WEAR"
    assert diagnosis["fmea_reference"] == "FM-1182"
    assert diagnosis["confidence"] == pytest.approx(0.87)
    assert diagnosis["recommended_action"] == "schedule_replacement"
    assert diagnosis["similar_work_order_reference"] == "WO-40218"
    assert len(diagnosis["evidence_items"]) == 4

    rejected = {
        alt["failure_mode_code"]: alt["rejection_reason"] for alt in diagnosis["alternatives"]
    }
    assert set(rejected) == {"MISALIGNMENT", "BRG_INNER_RACE_WEAR"}
    assert "2x" in rejected["MISALIGNMENT"]
    assert "BPFI" in rejected["BRG_INNER_RACE_WEAR"]

    assert body["rul"] == {"estimate_days": 18.0, "ci_low_days": 12.0, "ci_high_days": 26.0}

    proposal = body["proposal"]
    assert proposal["duration_hours"] == pytest.approx(6.0)
    assert proposal["rul_margin_days"] == pytest.approx(9.0)
    assert proposal["planned_changeover"] is True
    assert proposal["crew_available"] is True
    assert proposal["status"] == "proposed"

    part = proposal["part_checks"][0]
    assert part["sku"] == "BRG-6220-C3"
    assert part["quantity"] == 1
    assert part["in_stock"] is True
    assert part["location"] == "STORE-A"
    assert part["lead_time_days"] == 0
    assert part["currency"] == "INR"
    # Nothing is held before approval.
    assert part["status"] == "checked_not_reserved"
    assert part["reserved_at"] is None

    # Nothing downstream of approval exists yet.
    assert body["approval"] is None
    assert body["work_order"] is None
    assert body["technician_outcome"] is None


async def test_incident_detail_404s_for_unknown_id(api: AsyncClient, app_database: str) -> None:
    response = await api.get("/incidents/00000000-0000-4000-8000-000000000000")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
