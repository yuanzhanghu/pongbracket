"""Targeted coverage for small uncovered branches across scheduling/planning logic:

- planning.matches: empty-wave skip (55) and get_scheduled_matches_per_court (173-180)
- scheduling.elimination_seeding: "too few" (216) and "too many" (223) qualifier guards
- scheduling.handle_stage_activation.resolve_byes_in_activated_stage: non-elimination
  skip (164) and the empty-slot-1 walkover branch (187)
- scheduling.round_robin_groups: group_count<1 (57) and group too small (64) guards
"""

import pytest
from fastapi import HTTPException
from heliclockter import datetime_utc

from bracket.database import database
from bracket.logic.planning.matches import (
    get_scheduled_matches_per_court,
    schedule_all_unscheduled_matches,
)
from bracket.logic.scheduling.builder import build_matches_for_stage_item
from bracket.logic.scheduling.elimination_seeding import create_elimination_from_sources
from bracket.logic.scheduling.handle_stage_activation import resolve_byes_in_activated_stage
from bracket.logic.scheduling.round_robin_groups import create_round_robin_groups
from bracket.models.db.stage_item import EliminationSource, StageItemWithInputsCreate, StageType
from bracket.models.db.stage_item_inputs import (
    StageItemInputCreateBodyEmpty,
    StageItemInputCreateBodyFinal,
)
from bracket.schema import rounds as rounds_table
from bracket.sql.shared import sql_delete_stage_item_with_foreign_keys
from bracket.sql.stage_items import sql_create_stage_item_with_inputs
from bracket.sql.stages import get_full_tournament_details
from bracket.utils.dummy_records import (
    DUMMY_COURT1,
    DUMMY_STAGE1,
    DUMMY_STAGE2,
    DUMMY_STAGE_ITEM1,
    DUMMY_TEAM1,
)
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import inserted_court, inserted_stage, inserted_team


async def _round_robin(tournament_id: int, stage_id: int, name: str, team_count: int) -> int:
    item = await sql_create_stage_item_with_inputs(
        tournament_id,
        StageItemWithInputsCreate(
            stage_id=stage_id,
            name=name,
            type=StageType.ROUND_ROBIN,
            team_count=team_count,
            inputs=[StageItemInputCreateBodyEmpty(slot=i + 1) for i in range(team_count)],
        ),
    )
    return item.id


# --- planning.matches: empty wave skip (line 55) + per-court grouping (173-180) ---


@pytest.mark.asyncio(loop_scope="session")
async def test_schedule_skips_empty_wave_round(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """A round with no matches yields an empty wave, hitting the `continue`. (matches.py 55)"""
    tournament_id = auth_context.tournament.id
    async with (
        inserted_court(DUMMY_COURT1.model_copy(update={"tournament_id": tournament_id})),
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": tournament_id})
        ) as stage_inserted,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as team_1,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as team_2,
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
                        StageItemInputCreateBodyFinal(slot=1, team_id=team_1.id),
                        StageItemInputCreateBodyFinal(slot=2, team_id=team_2.id),
                    ],
                ),
            )
            await build_matches_for_stage_item(stage_item, tournament_id)

            # Add an extra round with NO matches. round_count grows to include it, so its
            # wave is empty -> schedule loop hits `if len(wave_matches) < 1: continue`.
            await database.execute(
                query=rounds_table.insert(),
                values={
                    "created": datetime_utc.now(),
                    "stage_item_id": stage_item.id,
                    "is_draft": False,
                    "name": "Empty Round",
                },
            )

            stages = await get_full_tournament_details(tournament_id)
            await schedule_all_unscheduled_matches(tournament_id, stages)
        finally:
            if stage_item is not None:
                await sql_delete_stage_item_with_foreign_keys(stage_item.id)


@pytest.mark.asyncio(loop_scope="session")
async def test_get_scheduled_matches_per_court(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """get_scheduled_matches_per_court groups scheduled matches by court. (matches.py 173-180)"""
    tournament_id = auth_context.tournament.id
    async with (
        inserted_court(DUMMY_COURT1.model_copy(update={"tournament_id": tournament_id})),
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": tournament_id})
        ) as stage_inserted,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as team_1,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as team_2,
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
                        StageItemInputCreateBodyFinal(slot=1, team_id=team_1.id),
                        StageItemInputCreateBodyFinal(slot=2, team_id=team_2.id),
                    ],
                ),
            )
            await build_matches_for_stage_item(stage_item, tournament_id)
            stages = await get_full_tournament_details(tournament_id)
            await schedule_all_unscheduled_matches(tournament_id, stages)

            # Re-fetch so matches now carry start_time/court_id.
            stages = await get_full_tournament_details(tournament_id)
            per_court = get_scheduled_matches_per_court(stages)
            assert isinstance(per_court, dict)
            # The single scheduled match is grouped under its court.
            assert sum(len(v) for v in per_court.values()) >= 1
        finally:
            if stage_item is not None:
                await sql_delete_stage_item_with_foreign_keys(stage_item.id)


# --- elimination_seeding guards (216, 223) ---


@pytest.mark.asyncio(loop_scope="session")
async def test_elimination_from_sources_too_few_qualifiers(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """Fewer than 2 qualifying positions is rejected. (elimination_seeding.py 216)"""
    tournament_id = auth_context.tournament.id
    async with (
        inserted_stage(DUMMY_STAGE1.model_copy(update={"tournament_id": tournament_id})) as stage_1,
        inserted_stage(DUMMY_STAGE2.model_copy(update={"tournament_id": tournament_id})) as stage_2,
    ):
        group_a = await _round_robin(tournament_id, stage_1.id, "A", 3)
        try:
            with pytest.raises(HTTPException) as exc_info:
                await create_elimination_from_sources(
                    tournament_id,
                    stage_2.id,
                    "Knockout",
                    [EliminationSource(stage_item_id=group_a, positions=1)],
                )
            assert exc_info.value.status_code == 400
            assert "至少需要选择 2" in exc_info.value.detail
        finally:
            await sql_delete_stage_item_with_foreign_keys(group_a)


@pytest.mark.asyncio(loop_scope="session")
async def test_elimination_from_sources_too_many_qualifiers(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """More than 64 qualifiers overflow a single bracket. (elimination_seeding.py 223)"""
    tournament_id = auth_context.tournament.id
    async with (
        inserted_stage(DUMMY_STAGE1.model_copy(update={"tournament_id": tournament_id})) as stage_1,
        inserted_stage(DUMMY_STAGE2.model_copy(update={"tournament_id": tournament_id})) as stage_2,
    ):
        # Two groups of 33 qualifiers -> 66 total -> bracket of 128 slots (> 64). A single
        # stage item is capped at 64 teams, so we need two sources to exceed 64 qualifiers.
        group_a = await _round_robin(tournament_id, stage_1.id, "A", 33)
        group_b = await _round_robin(tournament_id, stage_1.id, "B", 33)
        try:
            with pytest.raises(HTTPException) as exc_info:
                await create_elimination_from_sources(
                    tournament_id,
                    stage_2.id,
                    "Knockout",
                    [
                        EliminationSource(stage_item_id=group_a, positions=33),
                        EliminationSource(stage_item_id=group_b, positions=33),
                    ],
                )
            assert exc_info.value.status_code == 400
            assert "最多 64" in exc_info.value.detail
        finally:
            await sql_delete_stage_item_with_foreign_keys(group_a)
            await sql_delete_stage_item_with_foreign_keys(group_b)


# --- handle_stage_activation.resolve_byes_in_activated_stage (164, 187) ---


@pytest.mark.asyncio(loop_scope="session")
async def test_resolve_byes_handles_both_walkover_slots_and_skips_non_elimination(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """resolve_byes_in_activated_stage:
    - skips a non-elimination stage item (line 164)
    - awards the walkover when slot 1 is empty (empty1 branch, line 187) and when slot 2
      is empty (empty2 branch, line 185).
    """
    tournament_id = auth_context.tournament.id
    async with (
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": tournament_id})
        ) as stage_inserted,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as team_1,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as team_2,
    ):
        rr_item = elim_item = None
        try:
            # A round-robin item in the activated stage -> hits the non-elimination skip.
            rr_item = await sql_create_stage_item_with_inputs(
                tournament_id,
                StageItemWithInputsCreate(
                    stage_id=stage_inserted.id,
                    name="RR",
                    team_count=2,
                    type=StageType.ROUND_ROBIN,
                    ranking_id=auth_context.ranking.id,
                    inputs=[
                        StageItemInputCreateBodyFinal(slot=1, team_id=team_1.id),
                        StageItemInputCreateBodyFinal(slot=2, team_id=team_2.id),
                    ],
                ),
            )
            await build_matches_for_stage_item(rr_item, tournament_id)

            # A 4-slot single-elimination with the empties on slots 1 and 4 so the first
            # first-round match has empty slot 1 (empty1) and the second has empty slot 2
            # (empty2): both walkover branches fire.
            elim_item = await sql_create_stage_item_with_inputs(
                tournament_id,
                StageItemWithInputsCreate(
                    stage_id=stage_inserted.id,
                    name="Elim",
                    team_count=4,
                    type=StageType.SINGLE_ELIMINATION,
                    ranking_id=auth_context.ranking.id,
                    inputs=[
                        StageItemInputCreateBodyEmpty(slot=1),
                        StageItemInputCreateBodyFinal(slot=2, team_id=team_1.id),
                        StageItemInputCreateBodyFinal(slot=3, team_id=team_2.id),
                        StageItemInputCreateBodyEmpty(slot=4),
                    ],
                ),
            )
            await build_matches_for_stage_item(elim_item, tournament_id)

            await resolve_byes_in_activated_stage(tournament_id, stage_inserted.id)

            # The two first-round matches now have a walkover score recorded.
            stages = await get_full_tournament_details(tournament_id)
            elim = next(si for stage in stages for si in stage.stage_items if si.id == elim_item.id)
            first_round = min(elim.rounds, key=lambda r: r.id)
            scored = [
                m
                for m in first_round.matches
                if m.stage_item_input1_score or m.stage_item_input2_score
            ]
            # Two byes -> two walkover results.
            assert len(scored) == 2
            # One of them won via slot 1 (input1 score 0) and one via slot 2.
            assert any(m.stage_item_input1_score == 0 for m in scored)
            assert any(m.stage_item_input2_score == 0 for m in scored)
        finally:
            if elim_item is not None:
                await sql_delete_stage_item_with_foreign_keys(elim_item.id)
            if rr_item is not None:
                await sql_delete_stage_item_with_foreign_keys(rr_item.id)


# --- round_robin_groups guards (57, 64) ---


@pytest.mark.asyncio(loop_scope="session")
async def test_round_robin_groups_rejects_zero_groups(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """group_count < 1 is rejected. (round_robin_groups.py 57)"""
    tournament_id = auth_context.tournament.id
    async with inserted_stage(
        DUMMY_STAGE1.model_copy(update={"tournament_id": tournament_id})
    ) as stage_inserted:
        with pytest.raises(HTTPException) as exc_info:
            await create_round_robin_groups(
                tournament_id, stage_inserted.id, group_count=0, total_team_count=4
            )
        assert exc_info.value.status_code == 400
        assert "至少为 1" in exc_info.value.detail


@pytest.mark.asyncio(loop_scope="session")
async def test_round_robin_groups_rejects_too_small_groups(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """Groups smaller than 2 teams are rejected. (round_robin_groups.py 64)"""
    tournament_id = auth_context.tournament.id
    async with inserted_stage(
        DUMMY_STAGE1.model_copy(update={"tournament_id": tournament_id})
    ) as stage_inserted:
        # 3 teams over 2 groups -> [2, 1]; the group of 1 is too small.
        with pytest.raises(HTTPException) as exc_info:
            await create_round_robin_groups(
                tournament_id, stage_inserted.id, group_count=2, total_team_count=3
            )
        assert exc_info.value.status_code == 400
        assert "每组至少 2 队" in exc_info.value.detail
