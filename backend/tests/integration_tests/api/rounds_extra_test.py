"""
Extra tests for bracket/routes/rounds.py.
Covers deleting a round with matches (line 51) and creating a round
on a stage type that doesn't support it (line 81).
"""

import pytest

from bracket.models.db.stage_item import StageType
from bracket.models.db.stage_item_inputs import StageItemInputInsertable
from bracket.utils.dummy_records import (
    DUMMY_MATCH1,
    DUMMY_ROUND1,
    DUMMY_STAGE1,
    DUMMY_STAGE_ITEM1,
    DUMMY_TEAM1,
    DUMMY_TEAM2,
)
from bracket.utils.http import HTTPMethod
from tests.integration_tests.api.shared import send_tournament_request
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import (
    inserted_match,
    inserted_round,
    inserted_stage,
    inserted_stage_item,
    inserted_stage_item_input,
    inserted_team,
)


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_round_with_matches(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """Deleting a round should also delete its matches (line 51)."""
    async with (
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})),
        inserted_team(DUMMY_TEAM2.model_copy(update={"tournament_id": auth_context.tournament.id})),
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as stage_inserted,
        inserted_stage_item(
            DUMMY_STAGE_ITEM1.model_copy(
                update={
                    "stage_id": stage_inserted.id,
                    "ranking_id": auth_context.ranking.id,
                    "type": StageType.ROUND_ROBIN,
                }
            )
        ) as stage_item_inserted,
        inserted_round(
            DUMMY_ROUND1.model_copy(update={"stage_item_id": stage_item_inserted.id})
        ) as round_inserted,
        inserted_stage_item_input(
            StageItemInputInsertable(
                slot=0,
                team_id=None,
                tournament_id=auth_context.tournament.id,
                stage_item_id=stage_item_inserted.id,
            )
        ) as sii1,
        inserted_stage_item_input(
            StageItemInputInsertable(
                slot=1,
                team_id=None,
                tournament_id=auth_context.tournament.id,
                stage_item_id=stage_item_inserted.id,
            )
        ) as sii2,
        inserted_match(
            DUMMY_MATCH1.model_copy(
                update={
                    "round_id": round_inserted.id,
                    "stage_item_input1_id": sii1.id,
                    "stage_item_input2_id": sii2.id,
                    "court_id": None,
                }
            )
        ),
    ):
        response = await send_tournament_request(
            HTTPMethod.DELETE, f"rounds/{round_inserted.id}", auth_context, {}
        )
        assert response.get("success") is True


@pytest.mark.asyncio(loop_scope="session")
async def test_create_round_unsupported_stage_type(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """Creating a round on a ROUND_ROBIN stage_item -> 400 (line 81)."""
    async with (
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})),
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as stage_inserted,
        inserted_stage_item(
            DUMMY_STAGE_ITEM1.model_copy(
                update={
                    "stage_id": stage_inserted.id,
                    "ranking_id": auth_context.ranking.id,
                    "type": StageType.ROUND_ROBIN,
                }
            )
        ) as stage_item_inserted,
    ):
        response = await send_tournament_request(
            HTTPMethod.POST,
            "rounds",
            auth_context,
            json={"stage_item_id": stage_item_inserted.id},
        )
        assert response == {"detail": f"阶段类型 {StageType.ROUND_ROBIN} 不支持手动创建回合"}
