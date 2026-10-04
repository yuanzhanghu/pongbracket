import pytest

from bracket.logic.scheduling.builder import build_matches_for_stage_item
from bracket.models.db.match import (
    MatchRescheduleBody,
    MatchWithDetails,
    MatchWithDetailsDefinitive,
)
from bracket.models.db.stage_item import StageItemWithInputsCreate
from bracket.models.db.stage_item_inputs import (
    StageItemInputCreateBodyFinal,
    StageItemInputCreateBodyTentative,
)
from bracket.sql.shared import sql_delete_stage_item_with_foreign_keys
from bracket.sql.stage_items import sql_create_stage_item_with_inputs
from bracket.sql.stages import get_full_tournament_details
from bracket.utils.dummy_records import (
    DUMMY_COURT1,
    DUMMY_COURT2,
    DUMMY_STAGE2,
    DUMMY_STAGE_ITEM1,
    DUMMY_STAGE_ITEM3,
    DUMMY_TEAM1,
)
from bracket.utils.http import HTTPMethod
from bracket.utils.id_types import CourtId
from bracket.utils.types import assert_some
from tests.integration_tests.api.shared import (
    SUCCESS_RESPONSE,
    send_tournament_request,
)
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import (
    inserted_court,
    inserted_stage,
    inserted_team,
)


@pytest.mark.asyncio(loop_scope="session")
async def test_schedule_all_matches(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with (
        inserted_court(
            DUMMY_COURT1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ),
        inserted_stage(
            DUMMY_STAGE2.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as stage_inserted_1,
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
        stage_item_1 = await sql_create_stage_item_with_inputs(
            tournament_id,
            StageItemWithInputsCreate(
                stage_id=stage_inserted_1.id,
                name=DUMMY_STAGE_ITEM1.name,
                team_count=DUMMY_STAGE_ITEM1.team_count,
                type=DUMMY_STAGE_ITEM1.type,
                inputs=[
                    StageItemInputCreateBodyFinal(
                        slot=1,
                        team_id=team_inserted_1.id,
                    ),
                    StageItemInputCreateBodyFinal(
                        slot=2,
                        team_id=team_inserted_2.id,
                    ),
                    StageItemInputCreateBodyFinal(
                        slot=3,
                        team_id=team_inserted_3.id,
                    ),
                    StageItemInputCreateBodyFinal(
                        slot=4,
                        team_id=team_inserted_4.id,
                    ),
                ],
            ),
        )
        stage_item_2 = await sql_create_stage_item_with_inputs(
            tournament_id,
            StageItemWithInputsCreate(
                stage_id=stage_inserted_1.id,
                name=DUMMY_STAGE_ITEM3.name,
                team_count=2,
                type=DUMMY_STAGE_ITEM3.type,
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
        await build_matches_for_stage_item(stage_item_2, tournament_id)

        response = await send_tournament_request(
            HTTPMethod.POST,
            "schedule_matches",
            auth_context,
        )
        stages = await get_full_tournament_details(tournament_id)

        await sql_delete_stage_item_with_foreign_keys(stage_item_2.id)
        await sql_delete_stage_item_with_foreign_keys(stage_item_1.id)

    assert response == SUCCESS_RESPONSE

    stage_item = stages[0].stage_items[0]
    assert len(stage_item.rounds) == 3
    for round_ in stage_item.rounds:
        assert len(round_.matches) == 2


@pytest.mark.asyncio(loop_scope="session")
async def test_schedule_all_matches_multi_court_alignment_and_reschedule(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """With multiple courts, auto-scheduling must give each court its own contiguous
    position_in_schedule (0, 1, 2, ...) and align start times across courts row-by-row.

    Regression test for the wave rewrite that left position_in_schedule as a single
    global counter: rows past the first no longer lined up, and dragging any card on a
    non-first court raised a 500 because the per-court drag index no longer matched the
    stored (global) position.
    """
    async with (
        inserted_court(
            DUMMY_COURT1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as court1_inserted,
        inserted_court(
            DUMMY_COURT2.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as court2_inserted,
        inserted_stage(
            DUMMY_STAGE2.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as stage_inserted_1,
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
        stage_item_1 = await sql_create_stage_item_with_inputs(
            tournament_id,
            StageItemWithInputsCreate(
                stage_id=stage_inserted_1.id,
                name=DUMMY_STAGE_ITEM1.name,
                team_count=DUMMY_STAGE_ITEM1.team_count,
                type=DUMMY_STAGE_ITEM1.type,
                inputs=[
                    StageItemInputCreateBodyFinal(slot=1, team_id=team_inserted_1.id),
                    StageItemInputCreateBodyFinal(slot=2, team_id=team_inserted_2.id),
                    StageItemInputCreateBodyFinal(slot=3, team_id=team_inserted_3.id),
                    StageItemInputCreateBodyFinal(slot=4, team_id=team_inserted_4.id),
                ],
            ),
        )
        await build_matches_for_stage_item(stage_item_1, tournament_id)

        assert (
            await send_tournament_request(HTTPMethod.POST, "schedule_matches", auth_context)
            == SUCCESS_RESPONSE
        )

        stages = await get_full_tournament_details(tournament_id)
        scheduled = [
            match
            for stage in stages
            for si in stage.stage_items
            for round_ in si.rounds
            for match in round_.matches
            if match.start_time is not None
        ]

        matches_per_court: dict[CourtId, list[MatchWithDetailsDefinitive | MatchWithDetails]] = {}
        for match in scheduled:
            matches_per_court.setdefault(assert_some(match.court_id), []).append(match)
        for court_matches in matches_per_court.values():
            court_matches.sort(key=lambda m: assert_some(m.position_in_schedule))

        # Both courts are used (the wave spreads matches across them).
        assert set(matches_per_court) == {court1_inserted.id, court2_inserted.id}

        # Each court gets its own contiguous position_in_schedule 0..k-1, which is what
        # the drag/reschedule endpoint validates the sent per-court index against.
        for court_matches in matches_per_court.values():
            positions = [m.position_in_schedule for m in court_matches]
            assert positions == list(range(len(court_matches)))

        # Rows line up across courts: the i-th card on every court shares a start time.
        court1_rows = matches_per_court[court1_inserted.id]
        court2_rows = matches_per_court[court2_inserted.id]
        for row_court1, row_court2 in zip(court1_rows, court2_rows):
            assert row_court1.start_time == row_court2.start_time

        # Dragging a card on the second court must succeed, not raise a 500.
        dragged = court2_rows[1]
        assert (
            await send_tournament_request(
                HTTPMethod.POST,
                f"matches/{dragged.id}/reschedule",
                auth_context,
                json=MatchRescheduleBody(
                    old_court_id=court2_inserted.id,
                    old_position=1,
                    new_court_id=court2_inserted.id,
                    new_position=0,
                ).model_dump(),
            )
            == SUCCESS_RESPONSE
        )

        await sql_delete_stage_item_with_foreign_keys(stage_item_1.id)
