"""
Extra tests for bracket/routes/rankings.py.
Covers the update_ranking recalculation for single_elimination stage items
(lines 58-62).
"""

import pytest

from bracket.models.db.stage_item import StageType
from bracket.models.db.stage_item_inputs import StageItemInputInsertable
from bracket.utils.dummy_records import (
    DUMMY_RANKING1,
    DUMMY_STAGE1,
    DUMMY_STAGE_ITEM3,
    DUMMY_TEAM1,
)
from bracket.utils.http import HTTPMethod
from tests.integration_tests.api.shared import send_tournament_request
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import (
    inserted_ranking,
    inserted_stage,
    inserted_stage_item,
    inserted_stage_item_input,
    inserted_team,
)


@pytest.mark.asyncio(loop_scope="session")
async def test_update_ranking_single_elimination(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """Updating a ranking referenced by a single_elimination stage_item triggers
    recalculate_ranking_for_stage_item and update_inputs_in_complete_elimination_stage_item
    (lines 58-62).
    """
    async with (
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})),
        inserted_ranking(
            DUMMY_RANKING1.model_copy(
                update={"tournament_id": auth_context.tournament.id, "position": 1}
            )
        ) as ranking_inserted,
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as stage_inserted,
        inserted_stage_item(
            DUMMY_STAGE_ITEM3.model_copy(
                update={
                    "stage_id": stage_inserted.id,
                    "ranking_id": ranking_inserted.id,
                    "type": StageType.SINGLE_ELIMINATION,
                }
            )
        ) as stage_item_inserted,
        inserted_stage_item_input(
            StageItemInputInsertable(
                slot=0,
                team_id=None,
                tournament_id=auth_context.tournament.id,
                stage_item_id=stage_item_inserted.id,
            )
        ),
    ):
        body = {
            "win_points": "2.0",
            "draw_points": "1.0",
            "loss_points": "0.0",
            "add_score_points": False,
            "position": 1,
        }
        response = await send_tournament_request(
            HTTPMethod.PUT,
            f"rankings/{ranking_inserted.id}",
            auth_context,
            json=body,
        )
        assert response.get("success") is True
