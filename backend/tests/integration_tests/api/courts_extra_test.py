"""
Extra tests for bracket/routes/courts.py.
Covers deleting a court that is used by matches (lines 71-75, 78).
"""

import pytest

from bracket.models.db.match import MatchInsertable
from bracket.models.db.stage_item import StageType
from bracket.models.db.stage_item_inputs import StageItemInputInsertable
from bracket.utils.dummy_records import (
    DUMMY_COURT1,
    DUMMY_MATCH1,
    DUMMY_ROUND1,
    DUMMY_STAGE1,
    DUMMY_STAGE_ITEM1,
    DUMMY_TEAM1,
)
from bracket.utils.http import HTTPMethod
from tests.integration_tests.api.shared import send_tournament_request
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import (
    inserted_court,
    inserted_match,
    inserted_round,
    inserted_stage,
    inserted_stage_item,
    inserted_stage_item_input,
    inserted_team,
)


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_court_used_by_matches(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """Deleting a court that is used by a match -> 400 (lines 71-75, 78)."""
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
        inserted_round(
            DUMMY_ROUND1.model_copy(
                update={"stage_item_id": stage_item_inserted.id, "is_draft": True}
            )
        ) as round_inserted,
        inserted_court(
            DUMMY_COURT1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as court_inserted,
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
                    "court_id": court_inserted.id,
                }
            )
        ),
    ):
        response = await send_tournament_request(
            HTTPMethod.DELETE, f"courts/{court_inserted.id}", auth_context
        )
        assert "detail" in response
        assert "无法删除" in response["detail"]
