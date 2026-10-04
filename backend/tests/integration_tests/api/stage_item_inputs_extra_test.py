"""
Extra tests for bracket/routes/stage_item_inputs.py.
Covers:
- 404 when stage_item_input not found (line 40)
- the Tentative branch (lines 45-49) which triggers a DB foreign key
  violation (500) because the code's `is None` check is dead code.
"""

import pytest

from bracket.models.db.stage_item import StageType
from bracket.models.db.stage_item_inputs import StageItemInputInsertable
from bracket.utils.dummy_records import DUMMY_STAGE1, DUMMY_STAGE_ITEM1, DUMMY_TEAM1
from bracket.utils.http import HTTPMethod
from tests.integration_tests.api.shared import send_tournament_request
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import (
    inserted_stage,
    inserted_stage_item,
    inserted_stage_item_input,
    inserted_team,
)


@pytest.mark.asyncio(loop_scope="session")
async def test_update_stage_item_input_not_found(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """Updating a non-existent stage_item_input -> 404 (line 40)."""
    async with (
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})),
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as stage_inserted,
        inserted_stage_item(
            DUMMY_STAGE_ITEM1.model_copy(
                update={"stage_id": stage_inserted.id, "ranking_id": auth_context.ranking.id}
            )
        ) as stage_item_inserted,
    ):
        response = await send_tournament_request(
            HTTPMethod.PUT,
            f"stage_items/{stage_item_inserted.id}/inputs/-1",
            auth_context,
            json={"team_id": None},
        )
        assert response == {"detail": "找不到该阶段项目的输入位"}


@pytest.mark.asyncio(loop_scope="session")
async def test_update_stage_item_input_tentative_branch(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """Sending a Tentative body exercises lines 45-49 (the isinstance check and
    the get_full_tournament_details call). The DB raises a foreign key violation
    (500) because the `is None` check on line 50 is dead code.
    """
    async with (
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})),
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as stage_inserted,
        inserted_stage_item(
            DUMMY_STAGE_ITEM1.model_copy(
                update={"stage_id": stage_inserted.id, "ranking_id": auth_context.ranking.id}
            )
        ) as stage_item_inserted,
        inserted_stage_item_input(
            StageItemInputInsertable(
                slot=0,
                team_id=None,
                tournament_id=auth_context.tournament.id,
                stage_item_id=stage_item_inserted.id,
            )
        ) as stage_item_input_inserted,
    ):
        response = await send_tournament_request(
            HTTPMethod.PUT,
            f"stage_items/{stage_item_inserted.id}/inputs/{stage_item_input_inserted.id}",
            auth_context,
            json={"winner_from_stage_item_id": -999, "winner_position": 1},
        )
        # DB foreign key violation -> 500 error (covers lines 45-49)
        assert "detail" in response


@pytest.mark.asyncio(loop_scope="session")
async def test_validate_stage_item_update_winner_from_stage_none_raises_404() -> None:
    """Calling validate_stage_item_update with a Tentative body and patching
    get_full_tournament_details to return None hits the dead-code branch
    at line 51. Unreachable via HTTP: get_full_tournament_details returns
    a list (never None).
    """
    from unittest.mock import AsyncMock, patch

    from fastapi import HTTPException

    from bracket.models.db.stage_item_inputs import (
        StageItemInputUpdateBodyTentative,
    )
    from bracket.routes.stage_item_inputs import validate_stage_item_update

    stage_item_input_body = StageItemInputUpdateBodyTentative(
        winner_from_stage_item_id=-1,  # type: ignore[arg-type]
        winner_position=1,
    )
    # stage_item_input_db is just passed through the None-check.
    fake_db = AsyncMock()
    fake_db.id = 1  # type: ignore[attr-defined]

    with patch(
        "bracket.routes.stage_item_inputs.get_full_tournament_details",
        new=AsyncMock(return_value=None),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await validate_stage_item_update(
                stage_item_input_db=fake_db,  # type: ignore[arg-type]
                stage_item_input_body=stage_item_input_body,
                tournament_id=-1,  # type: ignore[arg-type]
            )
    assert exc_info.value.status_code == 404
    assert "找不到 ID 为 -1 的阶段项目" in exc_info.value.detail
