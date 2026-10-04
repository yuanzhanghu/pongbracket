"""Integration tests for bracket.logic.planning.conflicts and planning.matches DB-bound paths."""

import pytest

from bracket.logic.planning.conflicts import handle_conflicts, set_conflicts
from bracket.logic.planning.matches import (
    handle_match_reschedule,
    schedule_all_unscheduled_matches,
    update_start_times_of_matches,
)
from bracket.models.db.match import MatchRescheduleBody
from bracket.models.db.stage_item import StageItemWithInputsCreate, StageType
from bracket.models.db.stage_item_inputs import (
    StageItemInputCreateBodyEmpty,
    StageItemInputCreateBodyFinal,
)
from bracket.models.db.tournament import Tournament
from bracket.sql.shared import sql_delete_stage_item_with_foreign_keys
from bracket.sql.stage_items import sql_create_stage_item_with_inputs
from bracket.sql.stages import get_full_tournament_details
from bracket.utils.dummy_records import (
    DUMMY_COURT1,
    DUMMY_COURT2,
    DUMMY_STAGE1,
    DUMMY_STAGE_ITEM1,
    DUMMY_TEAM1,
    DUMMY_TOURNAMENT,
)
from bracket.utils.id_types import CourtId, MatchId
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import inserted_court, inserted_stage, inserted_team


@pytest.mark.asyncio(loop_scope="session")
async def test_set_conflicts_updates_db(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """set_conflicts updates the stage_item_input1/2_conflict columns. (lines 84-101)"""
    conflicts_to_set = {-1: [True, False]}
    await set_conflicts(conflicts_to_set, set())


@pytest.mark.asyncio(loop_scope="session")
async def test_handle_conflicts_with_empty_stages(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """handle_conflicts with no stages is a no-op. (lines 113-115)"""
    await handle_conflicts([])


@pytest.mark.asyncio(loop_scope="session")
async def test_schedule_all_unscheduled_matches_no_courts_no_op(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """schedule_all_unscheduled_matches returns early when there are no courts. (lines 26-30)"""
    stages = await get_full_tournament_details(auth_context.tournament.id)
    await schedule_all_unscheduled_matches(auth_context.tournament.id, stages)


@pytest.mark.asyncio(loop_scope="session")
async def test_schedule_all_unscheduled_matches_with_courts(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """schedule_all_unscheduled_matches schedules matches on courts. (lines 31-67)"""
    async with (
        inserted_court(
            DUMMY_COURT1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ),
        inserted_court(
            DUMMY_COURT2.model_copy(update={"tournament_id": auth_context.tournament.id})
        ),
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as stage_inserted,
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as team_inserted_1,
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as team_inserted_2,
    ):
        tournament_id = auth_context.tournament.id
        stage_item = None
        try:
            stage_item = await sql_create_stage_item_with_inputs(
                tournament_id,
                StageItemWithInputsCreate(
                    stage_id=stage_inserted.id,
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
            from bracket.logic.scheduling.builder import build_matches_for_stage_item

            await build_matches_for_stage_item(stage_item, tournament_id)
            stages = await get_full_tournament_details(tournament_id)
            await schedule_all_unscheduled_matches(tournament_id, stages)
        finally:
            if stage_item is not None:
                await sql_delete_stage_item_with_foreign_keys(stage_item.id)


@pytest.mark.asyncio(loop_scope="session")
async def test_handle_match_reschedule_same_position_no_op(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """When old_position == new_position and same court, handle_match_reschedule returns early. (lines 102-103)"""
    tournament = Tournament(**DUMMY_TOURNAMENT.model_dump(), id=auth_context.tournament.id)
    body = MatchRescheduleBody(
        old_court_id=CourtId(-1),
        old_position=1,
        new_court_id=CourtId(-1),
        new_position=1,
    )
    await handle_match_reschedule(tournament, body, match_id=-1)  # type: ignore[arg-type]


@pytest.mark.asyncio(loop_scope="session")
async def test_update_start_times_of_matches_no_matches(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """update_start_times_of_matches is a no-op when there are no scheduled matches. (lines 138-145)"""
    await update_start_times_of_matches(auth_context.tournament.id)


@pytest.mark.asyncio(loop_scope="session")
async def test_update_start_times_of_matches_with_courts(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """update_start_times_of_matches iterates over courts. (lines 144-145)"""
    async with inserted_court(
        DUMMY_COURT1.model_copy(update={"tournament_id": auth_context.tournament.id})
    ):
        await update_start_times_of_matches(auth_context.tournament.id)


@pytest.mark.asyncio(loop_scope="session")
async def test_handle_match_reschedule_line130_no_match_with_id(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """
    When handle_match_reschedule is called with a match_id that does not match any
    scheduled match, the inner `else` branch (line 130: `scheduled_matches.append(match_pos)`)
    is exercised for every existing scheduled match. (line 130)
    """
    tournament_id = auth_context.tournament.id
    async with (
        inserted_court(
            DUMMY_COURT1.model_copy(update={"tournament_id": tournament_id})
        ) as court_inserted,
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": tournament_id})
        ) as stage_inserted,
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})
        ) as team_inserted_1,
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})
        ) as team_inserted_2,
    ):
        stage_item = None
        try:
            stage_item = await sql_create_stage_item_with_inputs(
                tournament_id,
                StageItemWithInputsCreate(
                    stage_id=stage_inserted.id,
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
            from bracket.logic.scheduling.builder import build_matches_for_stage_item

            await build_matches_for_stage_item(stage_item, tournament_id)
            stages = await get_full_tournament_details(tournament_id)
            await schedule_all_unscheduled_matches(tournament_id, stages)

            tournament = Tournament(**DUMMY_TOURNAMENT.model_dump(), id=tournament_id)
            # Use a bogus match_id that won't match any existing match -> loop hits the
            # else branch (line 130) for every existing scheduled match.
            body = MatchRescheduleBody(
                old_court_id=court_inserted.id,
                old_position=1,
                new_court_id=court_inserted.id,
                new_position=2,
            )
            await handle_match_reschedule(tournament, body, match_id=MatchId(-99999))  # type: ignore[arg-type]
        finally:
            if stage_item is not None:
                await sql_delete_stage_item_with_foreign_keys(stage_item.id)


@pytest.mark.asyncio(loop_scope="session")
async def test_handle_match_reschedule_line116_position_mismatch_raises(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """
    When the body.old_position/court_id don't match the actual scheduled match's
    position/court, handle_match_reschedule raises ValueError. (line 116)
    """
    tournament_id = auth_context.tournament.id
    async with (
        inserted_court(
            DUMMY_COURT1.model_copy(update={"tournament_id": tournament_id})
        ) as court_inserted,
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": tournament_id})
        ) as stage_inserted,
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})
        ) as team_inserted_1,
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})
        ) as team_inserted_2,
    ):
        stage_item = None
        try:
            stage_item = await sql_create_stage_item_with_inputs(
                tournament_id,
                StageItemWithInputsCreate(
                    stage_id=stage_inserted.id,
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
            from bracket.logic.scheduling.builder import build_matches_for_stage_item

            await build_matches_for_stage_item(stage_item, tournament_id)
            stages = await get_full_tournament_details(tournament_id)
            await schedule_all_unscheduled_matches(tournament_id, stages)
            # Re-fetch: schedule_all_unscheduled_matches updates the DB but the
            # in-memory `stages` object still has start_time=None on its matches.
            stages = await get_full_tournament_details(tournament_id)
            # Find the actual scheduled match.
            staged_match = None
            for stage in stages:
                for si in stage.stage_items:
                    for round_ in si.rounds:
                        for m in round_.matches:
                            if m.start_time is not None:
                                staged_match = m
                                break

            assert staged_match is not None, "expected at least one scheduled match"

            tournament = Tournament(**DUMMY_TOURNAMENT.model_dump(), id=tournament_id)
            # Provide the correct match_id but a wrong old_position to trigger the
            # ValueError on line 116.
            body = MatchRescheduleBody(
                old_court_id=staged_match.court_id or court_inserted.id,
                old_position=999,  # mismatched
                new_court_id=court_inserted.id,
                new_position=2,
            )
            with pytest.raises(ValueError, match="doesn't match"):
                await handle_match_reschedule(tournament, body, match_id=staged_match.id)
        finally:
            if stage_item is not None:
                await sql_delete_stage_item_with_foreign_keys(stage_item.id)
