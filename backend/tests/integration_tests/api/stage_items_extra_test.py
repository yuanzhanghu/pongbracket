"""
Extra tests for bracket/routes/stage_items.py.
Covers the update with single_elimination and the None-dependency 400 path.
"""

import pytest

from bracket.models.db.stage_item import StageType
from bracket.utils.dummy_records import (
    DUMMY_STAGE1,
    DUMMY_STAGE_ITEM3,
    DUMMY_TEAM1,
    DUMMY_TEAM2,
)
from bracket.utils.http import HTTPMethod
from tests.integration_tests.api.shared import send_tournament_request
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import (
    inserted_stage,
    inserted_stage_item,
    inserted_team,
)


@pytest.mark.asyncio(loop_scope="session")
async def test_update_stage_item_single_elimination(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """Updating a single_elimination stage_item triggers elimination recalc (line 129)."""
    async with (
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})),
        inserted_team(DUMMY_TEAM2.model_copy(update={"tournament_id": auth_context.tournament.id})),
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as stage_inserted,
        inserted_stage_item(
            DUMMY_STAGE_ITEM3.model_copy(
                update={
                    "stage_id": stage_inserted.id,
                    "ranking_id": auth_context.ranking.id,
                    "type": StageType.SINGLE_ELIMINATION,
                }
            )
        ) as stage_item_inserted,
    ):
        body = {"name": "Updated Bracket", "ranking_id": auth_context.ranking.id}
        response = await send_tournament_request(
            HTTPMethod.PUT,
            f"stage_items/{stage_item_inserted.id}",
            auth_context,
            json=body,
        )
        assert response.get("success") is True


@pytest.mark.asyncio(loop_scope="session")
async def test_update_stage_item_none_dependency_raises_400() -> None:
    """When stage_item dependency returns None, update_stage_item raises 400
    (line 113). Unreachable via HTTP: get_stage_item raises 400 instead of
    returning None, so the dep never returns None to the route.
    """
    from fastapi import HTTPException

    from bracket.models.db.stage_item import StageItemUpdateBody
    from bracket.routes.stage_items import update_stage_item

    with pytest.raises(HTTPException) as exc_info:
        await update_stage_item(
            tournament_id=-1,  # type: ignore[arg-type]
            stage_item_id=-1,  # type: ignore[arg-type]
            stage_item_body=StageItemUpdateBody(name="x", ranking_id=-1),  # type: ignore[arg-type]
            _=None,  # type: ignore[arg-type]
            __=None,  # type: ignore[arg-type]
            stage_item=None,
        )
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "找不到对应的阶段"
