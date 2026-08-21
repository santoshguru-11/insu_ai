"""Asset endpoints."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.models.incident import Incident

pytestmark = pytest.mark.db


async def test_list_assets_returns_the_seeded_register(
    api: AsyncClient, seeded: dict[str, Incident]
) -> None:
    response = await api.get("/assets")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    codes = {item["asset_code"] for item in body["items"]}
    assert codes == {"CAL-04-DRIVE", "MIX-02-AGITATOR", "COAT-01-DRYER"}
    # Ordered by asset code, so the list is stable across runs.
    assert [item["asset_code"] for item in body["items"]] == sorted(codes)


async def test_list_assets_filters_combine(api: AsyncClient, seeded: dict[str, Incident]) -> None:
    by_criticality = await api.get("/assets", params={"criticality": "high"})
    assert {item["asset_code"] for item in by_criticality.json()["items"]} == {
        "CAL-04-DRIVE",
        "COAT-01-DRYER",
    }

    by_plant = await api.get("/assets", params={"plant_name": "Battery Plant"})
    assert by_plant.json()["total"] == 3

    combined = await api.get(
        "/assets", params={"criticality": "critical", "plant_name": "Battery Plant"}
    )
    assert [item["asset_code"] for item in combined.json()["items"]] == ["MIX-02-AGITATOR"]

    no_match = await api.get("/assets", params={"plant_name": "Nowhere Plant"})
    assert no_match.json() == {"items": [], "total": 0, "limit": 50, "offset": 0}


async def test_list_assets_paginates(api: AsyncClient, seeded: dict[str, Incident]) -> None:
    first = await api.get("/assets", params={"limit": 2, "offset": 0})
    second = await api.get("/assets", params={"limit": 2, "offset": 2})

    assert first.json()["total"] == second.json()["total"] == 3
    assert len(first.json()["items"]) == 2
    assert len(second.json()["items"]) == 1
    first_ids = {item["id"] for item in first.json()["items"]}
    second_ids = {item["id"] for item in second.json()["items"]}
    assert not first_ids & second_ids


async def test_asset_detail_includes_latest_incident(
    api: AsyncClient, main_incident: Incident
) -> None:
    response = await api.get(f"/assets/{main_incident.asset_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["asset_code"] == "CAL-04-DRIVE"
    assert body["name"] == "Calender Roll Drive Train"
    assert body["plant_name"] == "Battery Plant"
    assert body["line_name"] == "Calender Line 2"
    assert body["criticality"] == "high"
    assert body["latest_incident"]["trace_id"] == "tr_9f21"
    assert body["latest_incident"]["workflow_status"] == "approval_required"
    assert body["open_incident_count"] == 1


async def test_asset_detail_404s_for_unknown_id(api: AsyncClient, app_database: str) -> None:
    response = await api.get("/assets/00000000-0000-4000-8000-000000000000")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
