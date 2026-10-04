"""Integration tests for bracket.logic.scheduling.handle_stage_activation DB-bound paths."""

import pytest
from fastapi import HTTPException

from bracket.database import database
from bracket.logic.scheduling.handle_stage_activation import (
    get_team_rankings_lookup_for_tournament,
    get_team_update_for_input,
    get_updates_to_inputs_in_activated_stage,
    update_matches_in_activated_stage,
    update_matches_in_deactivated_stage,
)
from bracket.logic.scheduling.builder import build_matches_for_stage_item
from bracket.models.db.stage_item import StageItemWithInputsCreate, StageType
from bracket.models.db.stage_item_inputs import (
    StageItemInputCreateBodyEmpty,
    StageItemInputCreateBodyFinal,
    StageItemInputCreateBodyTentative,
)
from bracket.schema import stage_item_inputs
from bracket.sql.shared import sql_delete_stage_item_with_foreign_keys
from bracket.sql.stage_items import sql_create_stage_item_with_inputs
from bracket.sql.stages import get_full_tournament_details
from bracket.utils.dummy_records import (
    DUMMY_STAGE1,
    DUMMY_STAGE2,
    DUMMY_STAGE_ITEM1,
    DUMMY_STAGE_ITEM3,
    DUMMY_TEAM1,
)
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import inserted_stage, inserted_team


@pytest.mark.asyncio(loop_scope="session")
async def test_get_team_rankings_lookup_for_tournament(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """get_team_rankings_lookup_for_tournament returns rankings per stage item. (lines 88-100)"""
    async with inserted_stage(
        DUMMY_STAGE1.model_copy(update={"tournament_id": auth_context.tournament.id})
    ):
        stages = await get_full_tournament_details(auth_context.tournament.id)
        result = await get_team_rankings_lookup_for_tournament(auth_context.tournament.id, stages)
        # Empty stages -> empty lookup.
        assert isinstance(result, dict)


@pytest.mark.asyncio(loop_scope="session")
async def test_get_team_update_for_input_with_real_ranking(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """get_team_update_for_input returns a StageItemInputUpdate for a finalized input."""
    async with (
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as stage_inserted_1,
        inserted_stage(
            DUMMY_STAGE2.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as stage_inserted_2,
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as team_inserted_1,
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as team_inserted_2,
    ):
        tournament_id = auth_context.tournament.id
        stage_item_1 = stage_item_2 = None
        try:
            stage_item_1 = await sql_create_stage_item_with_inputs(
                tournament_id,
                StageItemWithInputsCreate(
                    stage_id=stage_inserted_1.id,
                    name=DUMMY_STAGE_ITEM1.name,
                    team_count=2,
                    type=StageType.SINGLE_ELIMINATION,
                    ranking_id=auth_context.ranking.id,
                    inputs=[
                        StageItemInputCreateBodyFinal(slot=1, team_id=team_inserted_1.id),
                        StageItemInputCreateBodyFinal(slot=2, team_id=team_inserted_2.id),
                    ],
                ),
            )
            stage_item_2 = await sql_create_stage_item_with_inputs(
                tournament_id,
                StageItemWithInputsCreate(
                    stage_id=stage_inserted_2.id,
                    name=DUMMY_STAGE_ITEM3.name,
                    team_count=2,
                    type=StageType.SINGLE_ELIMINATION,
                    ranking_id=auth_context.ranking.id,
                    inputs=[
                        StageItemInputCreateBodyTentative(
                            slot=1,
                            winner_from_stage_item_id=stage_item_1.id,
                            winner_position=1,
                        ),
                        StageItemInputCreateBodyTentative(
                            slot=2,
                            winner_from_stage_item_id=stage_item_1.id,
                            winner_position=2,
                        ),
                    ],
                ),
            )
            await build_matches_for_stage_item(stage_item_1, tournament_id)
            stages = await get_full_tournament_details(tournament_id)
            rankings = await get_team_rankings_lookup_for_tournament(tournament_id, stages)

            from bracket.models.db.stage_item_inputs import StageItemInputTentative
            from bracket.sql.stage_item_inputs import get_stage_item_input_by_id

            # Find the tentative inputs created for stage_item_2 by querying
            # stage_item_inputs directly (get_full_tournament_details groups
            # tentative inputs together because their team_id is NULL).
            input_rows = await database.fetch_all(
                query=stage_item_inputs.select().where(
                    stage_item_inputs.c.stage_item_id == stage_item_2.id,
                    stage_item_inputs.c.winner_from_stage_item_id.is_not(None),
                )
            )
            inputs = [StageItemInputTentative.model_validate(dict(row)) for row in input_rows]
            assert len(inputs) == 2
            tentative_input_1 = inputs[0]
            # update_matches_in_activated_stage first.
            await update_matches_in_activated_stage(tournament_id, stage_inserted_2.id)

            # Now both should be finalized.
            finalized = await get_stage_item_input_by_id(tournament_id, tentative_input_1.id)
            assert finalized is not None

            # Now the lookup should map stage_item_1 to its team ranking.
            result = await get_team_update_for_input(tournament_id, tentative_input_1, rankings)
            assert result is not None
        finally:
            if stage_item_2 is not None:
                await sql_delete_stage_item_with_foreign_keys(stage_item_2.id)
            if stage_item_1 is not None:
                await sql_delete_stage_item_with_foreign_keys(stage_item_1.id)


@pytest.mark.asyncio(loop_scope="session")
async def test_get_updates_to_inputs_in_activated_stage(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """get_updates_to_inputs_in_activated_stage returns empty dict when stage has no tentative inputs. (lines 103-127)"""
    async with inserted_stage(
        DUMMY_STAGE1.model_copy(update={"tournament_id": auth_context.tournament.id})
    ) as stage_inserted:
        result = await get_updates_to_inputs_in_activated_stage(
            auth_context.tournament.id, stage_inserted.id
        )
        assert result == {}


@pytest.mark.asyncio(loop_scope="session")
async def test_get_updates_to_inputs_in_activated_stage_with_tentative_inputs(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """Activation maps tentative inputs to teams from the previous stage's ranking."""
    async with (
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as stage_inserted_1,
        inserted_stage(
            DUMMY_STAGE2.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as stage_inserted_2,
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as team_inserted_1,
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as team_inserted_2,
    ):
        tournament_id = auth_context.tournament.id
        stage_item_1 = stage_item_2 = None
        try:
            stage_item_1 = await sql_create_stage_item_with_inputs(
                tournament_id,
                StageItemWithInputsCreate(
                    stage_id=stage_inserted_1.id,
                    name=DUMMY_STAGE_ITEM1.name,
                    team_count=2,
                    type=StageType.SINGLE_ELIMINATION,
                    ranking_id=auth_context.ranking.id,
                    inputs=[
                        StageItemInputCreateBodyFinal(slot=1, team_id=team_inserted_1.id),
                        StageItemInputCreateBodyFinal(slot=2, team_id=team_inserted_2.id),
                    ],
                ),
            )
            stage_item_2 = await sql_create_stage_item_with_inputs(
                tournament_id,
                StageItemWithInputsCreate(
                    stage_id=stage_inserted_2.id,
                    name=DUMMY_STAGE_ITEM3.name,
                    team_count=2,
                    type=StageType.SINGLE_ELIMINATION,
                    ranking_id=auth_context.ranking.id,
                    inputs=[
                        StageItemInputCreateBodyTentative(
                            slot=1,
                            winner_from_stage_item_id=stage_item_1.id,
                            winner_position=1,
                        ),
                        StageItemInputCreateBodyTentative(
                            slot=2,
                            winner_from_stage_item_id=stage_item_1.id,
                            winner_position=2,
                        ),
                    ],
                ),
            )
            await build_matches_for_stage_item(stage_item_1, tournament_id)

            result = await get_updates_to_inputs_in_activated_stage(
                tournament_id, stage_inserted_2.id
            )
            # The result should map stage_item_2.id to a list of input updates.
            assert stage_item_2.id in result
        finally:
            if stage_item_2 is not None:
                await sql_delete_stage_item_with_foreign_keys(stage_item_2.id)
            if stage_item_1 is not None:
                await sql_delete_stage_item_with_foreign_keys(stage_item_1.id)


@pytest.mark.asyncio(loop_scope="session")
async def test_update_matches_in_activated_stage(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """update_matches_in_activated_stage applies team_id updates to tentative inputs."""
    async with inserted_stage(
        DUMMY_STAGE1.model_copy(update={"tournament_id": auth_context.tournament.id})
    ) as stage_inserted:
        # No tentative inputs in this stage -> no-op.
        await update_matches_in_activated_stage(auth_context.tournament.id, stage_inserted.id)


@pytest.mark.asyncio(loop_scope="session")
async def test_update_matches_in_deactivated_stage(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """update_matches_in_deactivated_stage clears team_ids for tentative inputs. (lines 142-153)"""
    async with (
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as stage_inserted_1,
        inserted_stage(
            DUMMY_STAGE2.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as stage_inserted_2,
    ):
        tournament_id = auth_context.tournament.id
        stage_item_1 = stage_item_2 = None
        try:
            stage_item_1 = await sql_create_stage_item_with_inputs(
                tournament_id,
                StageItemWithInputsCreate(
                    stage_id=stage_inserted_1.id,
                    name=DUMMY_STAGE_ITEM1.name,
                    team_count=2,
                    type=StageType.SINGLE_ELIMINATION,
                    ranking_id=auth_context.ranking.id,
                    inputs=[
                        StageItemInputCreateBodyEmpty(slot=1),
                        StageItemInputCreateBodyEmpty(slot=2),
                    ],
                ),
            )
            stage_item_2 = await sql_create_stage_item_with_inputs(
                tournament_id,
                StageItemWithInputsCreate(
                    stage_id=stage_inserted_2.id,
                    name=DUMMY_STAGE_ITEM3.name,
                    team_count=2,
                    type=StageType.SINGLE_ELIMINATION,
                    ranking_id=auth_context.ranking.id,
                    inputs=[
                        StageItemInputCreateBodyTentative(
                            slot=1,
                            winner_from_stage_item_id=stage_item_1.id,
                            winner_position=1,
                        ),
                        StageItemInputCreateBodyTentative(
                            slot=2,
                            winner_from_stage_item_id=stage_item_1.id,
                            winner_position=2,
                        ),
                    ],
                ),
            )
            stages = await get_full_tournament_details(tournament_id)
            stage_with_items = next(s for s in stages if s.id == stage_inserted_2.id)
            await update_matches_in_deactivated_stage(tournament_id, stage_with_items)
        finally:
            if stage_item_2 is not None:
                await sql_delete_stage_item_with_foreign_keys(stage_item_2.id)
            if stage_item_1 is not None:
                await sql_delete_stage_item_with_foreign_keys(stage_item_1.id)


@pytest.mark.asyncio(loop_scope="session")
async def test_get_team_update_for_input_empty_target_raises(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """
    When the target stage_item_input resolved from a previous stage's ranking is
    `StageItemInputEmpty` (i.e. the previous stage still has unassigned inputs),
    `get_team_update_for_input` raises HTTPException. (line 75)
    """
    async with (
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as stage_inserted_1,
        inserted_stage(
            DUMMY_STAGE2.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as stage_inserted_2,
    ):
        tournament_id = auth_context.tournament.id
        stage_item_1 = stage_item_2 = None
        try:
            # stage_item_1: ROUND_ROBIN with EMPTY inputs (no teams assigned).
            # This gives it a ranking whose entries are the Empty inputs.
            stage_item_1 = await sql_create_stage_item_with_inputs(
                tournament_id,
                StageItemWithInputsCreate(
                    stage_id=stage_inserted_1.id,
                    name=DUMMY_STAGE_ITEM1.name,
                    team_count=2,
                    type=StageType.ROUND_ROBIN,
                    ranking_id=auth_context.ranking.id,
                    inputs=[
                        StageItemInputCreateBodyEmpty(slot=1),
                        StageItemInputCreateBodyEmpty(slot=2),
                    ],
                ),
            )
            # Build matches for stage_item_1 so its (empty) inputs appear in
            # the ranking, giving stage_item_2's tentative inputs an Empty
            # target to resolve to.
            await build_matches_for_stage_item(stage_item_1, tournament_id)
            # stage_item_2: tentative inputs referencing stage_item_1.
            stage_item_2 = await sql_create_stage_item_with_inputs(
                tournament_id,
                StageItemWithInputsCreate(
                    stage_id=stage_inserted_2.id,
                    name=DUMMY_STAGE_ITEM3.name,
                    team_count=2,
                    type=StageType.SINGLE_ELIMINATION,
                    ranking_id=auth_context.ranking.id,
                    inputs=[
                        StageItemInputCreateBodyTentative(
                            slot=1,
                            winner_from_stage_item_id=stage_item_1.id,
                            winner_position=1,
                        ),
                        StageItemInputCreateBodyTentative(
                            slot=2,
                            winner_from_stage_item_id=stage_item_1.id,
                            winner_position=2,
                        ),
                    ],
                ),
            )
            stages = await get_full_tournament_details(tournament_id)
            rankings = await get_team_rankings_lookup_for_tournament(tournament_id, stages)

            # Fetch the tentative inputs we just created.
            input_rows = await database.fetch_all(
                query=stage_item_inputs.select().where(
                    stage_item_inputs.c.stage_item_id == stage_item_2.id,
                    stage_item_inputs.c.winner_from_stage_item_id.is_not(None),
                )
            )
            from bracket.models.db.stage_item_inputs import StageItemInputTentative

            tentative_inputs = [
                StageItemInputTentative.model_validate(dict(row)) for row in input_rows
            ]
            assert len(tentative_inputs) == 2

            # The target input from stage_item_1's ranking is an Empty input
            # -> get_team_update_for_input raises HTTPException.
            with pytest.raises(HTTPException) as exc_info:
                await get_team_update_for_input(tournament_id, tentative_inputs[0], rankings)
            assert exc_info.value.status_code == 400
            assert "每个阶段项目" in exc_info.value.detail
        finally:
            if stage_item_2 is not None:
                await sql_delete_stage_item_with_foreign_keys(stage_item_2.id)
            if stage_item_1 is not None:
                await sql_delete_stage_item_with_foreign_keys(stage_item_1.id)
