"""Integration tests for bracket.logic.ranking.elimination DB-bound paths."""

import pytest

from bracket.logic.ranking.elimination import (
    update_inputs_in_complete_elimination_stage_item,
    update_inputs_in_subsequent_elimination_rounds,
)
from bracket.logic.scheduling.builder import build_matches_for_stage_item
from bracket.models.db.stage_item import StageItemWithInputsCreate, StageType
from bracket.models.db.stage_item_inputs import StageItemInputCreateBodyFinal
from bracket.sql.shared import sql_delete_stage_item_with_foreign_keys
from bracket.sql.stage_items import sql_create_stage_item_with_inputs
from bracket.utils.dummy_records import (
    DUMMY_STAGE1,
    DUMMY_STAGE_ITEM1,
    DUMMY_TEAM1,
)
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import inserted_stage, inserted_team


@pytest.mark.asyncio(loop_scope="session")
async def test_update_inputs_in_subsequent_elimination_rounds_no_match_ids(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """update_inputs_in_subsequent_elimination_rounds with no match_ids updates all rounds. (lines 80-84)"""
    async with (
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as stage_inserted,
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as team_inserted_1,
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as team_inserted_2,
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as team_inserted_3,
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as team_inserted_4,
    ):
        tournament_id = auth_context.tournament.id
        stage_item = None
        try:
            stage_item = await sql_create_stage_item_with_inputs(
                tournament_id,
                StageItemWithInputsCreate(
                    stage_id=stage_inserted.id,
                    name=DUMMY_STAGE_ITEM1.name,
                    team_count=DUMMY_STAGE_ITEM1.team_count,
                    type=StageType.SINGLE_ELIMINATION,
                    ranking_id=auth_context.ranking.id,
                    inputs=[
                        StageItemInputCreateBodyFinal(slot=1, team_id=team_inserted_1.id),
                        StageItemInputCreateBodyFinal(slot=2, team_id=team_inserted_2.id),
                        StageItemInputCreateBodyFinal(slot=3, team_id=team_inserted_3.id),
                        StageItemInputCreateBodyFinal(slot=4, team_id=team_inserted_4.id),
                    ],
                ),
            )
            await build_matches_for_stage_item(stage_item, tournament_id)

            from bracket.sql.stages import get_full_tournament_details

            stages = await get_full_tournament_details(tournament_id)
            stage_with_items = stages[0]

            # Use the first round's id for current_round_id; no match_ids.
            current_round_id = stage_with_items.stage_items[0].rounds[0].id
            await update_inputs_in_subsequent_elimination_rounds(
                current_round_id=current_round_id,
                stage_item=stage_with_items.stage_items[0],
                match_ids=None,
            )
        finally:
            if stage_item is not None:
                await sql_delete_stage_item_with_foreign_keys(stage_item.id)


@pytest.mark.asyncio(loop_scope="session")
async def test_update_inputs_in_complete_elimination_stage_item(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """update_inputs_in_complete_elimination_stage_item loops over all rounds. (lines 89-93)"""
    async with (
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as stage_inserted,
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as team_inserted_1,
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as team_inserted_2,
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as team_inserted_3,
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as team_inserted_4,
    ):
        tournament_id = auth_context.tournament.id
        stage_item = None
        try:
            stage_item = await sql_create_stage_item_with_inputs(
                tournament_id,
                StageItemWithInputsCreate(
                    stage_id=stage_inserted.id,
                    name=DUMMY_STAGE_ITEM1.name,
                    team_count=DUMMY_STAGE_ITEM1.team_count,
                    type=StageType.SINGLE_ELIMINATION,
                    ranking_id=auth_context.ranking.id,
                    inputs=[
                        StageItemInputCreateBodyFinal(slot=1, team_id=team_inserted_1.id),
                        StageItemInputCreateBodyFinal(slot=2, team_id=team_inserted_2.id),
                        StageItemInputCreateBodyFinal(slot=3, team_id=team_inserted_3.id),
                        StageItemInputCreateBodyFinal(slot=4, team_id=team_inserted_4.id),
                    ],
                ),
            )
            await build_matches_for_stage_item(stage_item, tournament_id)

            from bracket.sql.stages import get_full_tournament_details

            stages = await get_full_tournament_details(tournament_id)
            await update_inputs_in_complete_elimination_stage_item(stages[0].stage_items[0])
        finally:
            if stage_item is not None:
                await sql_delete_stage_item_with_foreign_keys(stage_item.id)
