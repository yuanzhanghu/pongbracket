import pytest

from bracket.logic.scheduling.builder import build_matches_for_stage_item
from bracket.models.db.match import MatchBody, MatchWithDetailsDefinitive
from bracket.models.db.stage_item import StageItemWithInputsCreate
from bracket.models.db.stage_item_inputs import (
    StageItemInputCreateBodyEmpty,
    StageItemInputCreateBodyFinal,
    StageItemInputCreateBodyTentative,
)
from bracket.models.db.util import StageWithStageItems
from bracket.sql.matches import sql_update_match
from bracket.sql.shared import sql_delete_stage_item_with_foreign_keys
from bracket.sql.stage_items import sql_create_stage_item_with_inputs
from bracket.sql.stages import get_full_tournament_details
from bracket.utils.dummy_records import (
    DUMMY_COURT1,
    DUMMY_STAGE1,
    DUMMY_STAGE2,
    DUMMY_STAGE_ITEM1,
    DUMMY_STAGE_ITEM3,
    DUMMY_TEAM1,
)
from bracket.utils.http import HTTPMethod
from tests.integration_tests.api.shared import SUCCESS_RESPONSE, send_tournament_request
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import (
    inserted_court,
    inserted_stage,
    inserted_team,
)


@pytest.mark.asyncio(loop_scope="session")
async def test_activate_next_stage(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with (
        inserted_court(
            DUMMY_COURT1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ),
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
                stage_id=stage_inserted_2.id,
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

        # Set match score to get a winner (team 2) that goes to the next round
        [prev_stage, _] = await get_full_tournament_details(auth_context.tournament.id)
        match1 = prev_stage.stage_items[0].rounds[0].matches[0]
        assert isinstance(match1, MatchWithDetailsDefinitive)
        assert match1.stage_item_input2.team_id == team_inserted_2.id
        await sql_update_match(
            match1.id,
            MatchBody(**match1.model_copy(update={"stage_item_input2_score": 42}).model_dump()),
            auth_context.tournament,
        )

        response = await send_tournament_request(
            HTTPMethod.POST, "stages/activate?direction=next", auth_context, json={}
        )
        [_, next_stage] = await get_full_tournament_details(auth_context.tournament.id)

        await sql_delete_stage_item_with_foreign_keys(stage_item_2.id)
        await sql_delete_stage_item_with_foreign_keys(stage_item_1.id)

    assert response == SUCCESS_RESPONSE

    assert isinstance(next_stage, StageWithStageItems)
    # assert isinstance(next_stage.stage_items[0].rounds[0].matches[0], MatchWithDetailsDefinitive)
    # assert (
    #     next_stage.stage_items[0].rounds[0].matches[0].stage_item_input1.team_id
    #     == team_inserted_2.id
    # )


@pytest.mark.asyncio(loop_scope="session")
async def test_activate_next_stage_resolves_bye(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """An elimination match with one empty slot is auto-resolved as a walkover on
    activation: the present team wins so it advances without a played match."""
    async with (
        inserted_court(
            DUMMY_COURT1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ),
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
        stage_item_1 = await sql_create_stage_item_with_inputs(
            tournament_id,
            StageItemWithInputsCreate(
                stage_id=stage_inserted_1.id,
                name=DUMMY_STAGE_ITEM1.name,
                team_count=2,
                type=DUMMY_STAGE_ITEM1.type,
                inputs=[
                    StageItemInputCreateBodyFinal(slot=1, team_id=team_inserted_1.id),
                    StageItemInputCreateBodyFinal(slot=2, team_id=team_inserted_2.id),
                ],
            ),
        )
        # Single-elimination with one real input (winner of the group) and one empty slot.
        stage_item_2 = await sql_create_stage_item_with_inputs(
            tournament_id,
            StageItemWithInputsCreate(
                stage_id=stage_inserted_2.id,
                name=DUMMY_STAGE_ITEM3.name,
                team_count=2,
                type=DUMMY_STAGE_ITEM3.type,
                inputs=[
                    StageItemInputCreateBodyTentative(
                        slot=1,
                        winner_from_stage_item_id=stage_item_1.id,
                        winner_position=1,
                    ),
                    StageItemInputCreateBodyEmpty(slot=2),
                ],
            ),
        )
        await build_matches_for_stage_item(stage_item_1, tournament_id)
        await build_matches_for_stage_item(stage_item_2, tournament_id)

        # Score the group match so a clear winner qualifies as "1st".
        [prev_stage, _] = await get_full_tournament_details(tournament_id)
        group_match = prev_stage.stage_items[0].rounds[0].matches[0]
        assert isinstance(group_match, MatchWithDetailsDefinitive)
        await sql_update_match(
            group_match.id,
            MatchBody(**group_match.model_copy(update={"stage_item_input1_score": 9}).model_dump()),
            auth_context.tournament,
        )

        response = await send_tournament_request(
            HTTPMethod.POST, "stages/activate?direction=next", auth_context, json={}
        )

        [_, next_stage] = await get_full_tournament_details(tournament_id)
        bye_match = next_stage.stage_items[0].rounds[0].matches[0]

        await sql_delete_stage_item_with_foreign_keys(stage_item_2.id)
        await sql_delete_stage_item_with_foreign_keys(stage_item_1.id)

    assert response == SUCCESS_RESPONSE
    # The present team (slot 1) wins by walkover; the empty slot (slot 2) scores 0.
    assert bye_match.stage_item_input2_score == 0
    assert bye_match.stage_item_input1_score == bye_match.best_of // 2 + 1


@pytest.mark.asyncio(loop_scope="session")
async def test_activate_next_stage_propagates_bye_winner_to_next_round(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """A walkover winner must be filled into the subsequent round on activation, not stay
    as a 'winner of match X' placeholder until the bye match score is manually re-saved."""
    async with (
        inserted_court(
            DUMMY_COURT1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ),
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ),
        inserted_stage(
            DUMMY_STAGE2.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as stage_inserted_2,
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as team_inserted_1,
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as team_inserted_2,
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as team_inserted_3,
    ):
        tournament_id = auth_context.tournament.id
        # 4-slot elimination: match 1 is a bye (team 1 vs empty), match 2 is a real match.
        stage_item = await sql_create_stage_item_with_inputs(
            tournament_id,
            StageItemWithInputsCreate(
                stage_id=stage_inserted_2.id,
                name=DUMMY_STAGE_ITEM3.name,
                team_count=4,
                type=DUMMY_STAGE_ITEM3.type,
                inputs=[
                    StageItemInputCreateBodyFinal(slot=1, team_id=team_inserted_1.id),
                    StageItemInputCreateBodyEmpty(slot=2),
                    StageItemInputCreateBodyFinal(slot=3, team_id=team_inserted_2.id),
                    StageItemInputCreateBodyFinal(slot=4, team_id=team_inserted_3.id),
                ],
            ),
        )
        await build_matches_for_stage_item(stage_item, tournament_id)

        response = await send_tournament_request(
            HTTPMethod.POST, "stages/activate?direction=next", auth_context, json={}
        )

        [_, next_stage] = await get_full_tournament_details(tournament_id)
        rounds = sorted(next_stage.stage_items[0].rounds, key=lambda round_: round_.id)
        bye_match = rounds[0].matches[0]
        final_match = rounds[1].matches[0]

        await sql_delete_stage_item_with_foreign_keys(stage_item.id)

    assert response == SUCCESS_RESPONSE
    # The bye winner is propagated into the final; the other slot awaits the real match.
    assert final_match.stage_item_input1_winner_from_match_id == bye_match.id
    assert final_match.stage_item_input1_id == bye_match.stage_item_input1_id
    assert final_match.stage_item_input2_id is None
    assert bye_match.stage_item_input1_score > 0
