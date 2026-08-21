"""Asset endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import SessionDep
from app.core.exceptions import NotFoundError
from app.models.enums import AssetStatus, Criticality
from app.repositories.asset import AssetRepository
from app.repositories.incident import IncidentRepository
from app.schemas.asset import AssetDetail, AssetRead, LatestIncidentSummary
from app.schemas.common import ErrorResponse, Page

router = APIRouter(prefix="/assets", tags=["assets"])


@router.get(
    "",
    response_model=Page[AssetRead],
    summary="List assets",
    description=(
        "Paginated asset register, ordered by asset code. All filters are "
        "optional and combine with AND."
    ),
)
async def list_assets(
    session: SessionDep,
    criticality: Annotated[
        Criticality | None, Query(description="Only assets at this criticality.")
    ] = None,
    asset_status: Annotated[
        AssetStatus | None,
        Query(alias="status", description="Only assets in this operational status."),
    ] = None,
    plant_name: Annotated[
        str | None, Query(description="Exact plant name match.", examples=["Battery Plant"])
    ] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[AssetRead]:
    repository = AssetRepository(session)
    rows = await repository.list_filtered(
        criticality=criticality,
        status=asset_status,
        plant_name=plant_name,
        limit=limit,
        offset=offset,
    )
    total = await repository.count_filtered(
        criticality=criticality, status=asset_status, plant_name=plant_name
    )
    return Page[AssetRead](
        items=[AssetRead.model_validate(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{asset_id}",
    response_model=AssetDetail,
    summary="Get an asset",
    description="Asset record plus a summary of its most recently detected incident.",
    responses={status.HTTP_404_NOT_FOUND: {"model": ErrorResponse}},
)
async def get_asset(asset_id: uuid.UUID, session: SessionDep) -> AssetDetail:
    asset = await AssetRepository(session).get(asset_id)
    if asset is None:
        raise NotFoundError(f"No asset with id {asset_id}.", details={"asset_id": str(asset_id)})

    incidents = IncidentRepository(session)
    latest = await incidents.latest_for_asset(asset_id)
    return AssetDetail(
        **AssetRead.model_validate(asset).model_dump(),
        latest_incident=(
            LatestIncidentSummary.model_validate(latest) if latest is not None else None
        ),
        open_incident_count=await incidents.count_open_for_asset(asset_id),
    )
