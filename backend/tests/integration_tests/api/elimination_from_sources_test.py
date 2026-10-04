import pytest

from bracket.models.db.stage_item import StageItemWithInputsCreate, StageType
from bracket.models.db.stage_item_inputs import StageItemInputCreateBodyEmpty
from bracket.sql.shared import sql_delete_stage_item_with_foreign_keys
from bracket.sql.stage_items import sql_create_stage_item_with_inputs
from bracket.sql.stages import get_full_tournament_details
from bracket.utils.dummy_records import DUMMY_STAGE1, DUMMY_STAGE2
from bracket.utils.http import HTTPMethod
from tests.integration_tests.api.shared import send_tournament_request
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import inserted_stage


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


@pytest.mark.asyncio(loop_scope="session")
async def test_create_elimination_from_sources_seeds_and_byes(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    tournament_id = auth_context.tournament.id
    async with (
        inserted_stage(DUMMY_STAGE1.model_copy(update={"tournament_id": tournament_id})) as stage_1,
        inserted_stage(DUMMY_STAGE2.model_copy(update={"tournament_id": tournament_id})) as stage_2,
    ):
        # Two groups of 3 -> 6 qualifiers -> 8-slot bracket with 2 byes.
        group_a = await _round_robin(tournament_id, stage_1.id, "A", 3)
        group_b = await _round_robin(tournament_id, stage_1.id, "B", 3)

        response = await send_tournament_request(
            HTTPMethod.POST,
            "stage_items/elimination_from_sources",
            auth_context,
            json={
                "stage_id": stage_2.id,
                "name": "Knockout",
                "sources": [
                    {"stage_item_id": group_a, "positions": 3},
                    {"stage_item_id": group_b, "positions": 3},
                ],
            },
        )

        [stage] = [
            stage
            for stage in await get_full_tournament_details(tournament_id)
            if stage.id == stage_2.id
        ]
        [bracket] = stage.stage_items
        inputs = sorted(bracket.inputs, key=lambda inp: inp.slot)
        source_by_slot = [inp.winner_from_stage_item_id for inp in inputs]
        # First-round matches are slot pairs (1,2), (3,4), ...
        same_group_first_round = sum(
            1
            for i in range(0, len(inputs), 2)
            if source_by_slot[i] is not None and source_by_slot[i] == source_by_slot[i + 1]
        )

        await sql_delete_stage_item_with_foreign_keys(bracket.id)
        await sql_delete_stage_item_with_foreign_keys(group_a)
        await sql_delete_stage_item_with_foreign_keys(group_b)

    assert response == {"success": True}
    assert bracket.type == StageType.SINGLE_ELIMINATION
    assert bracket.team_count == 8
    assert sum(1 for s in source_by_slot if s is None) == 2  # 2 byes
    assert same_group_first_round == 0


@pytest.mark.asyncio(loop_scope="session")
async def test_create_elimination_from_sources_take_bottom(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    tournament_id = auth_context.tournament.id
    async with (
        inserted_stage(DUMMY_STAGE1.model_copy(update={"tournament_id": tournament_id})) as stage_1,
        inserted_stage(DUMMY_STAGE2.model_copy(update={"tournament_id": tournament_id})) as stage_2,
    ):
        # Unequal groups: bottom 2 of a group of 4 are positions 3-4, of a group of 3
        # positions 2-3.
        group_a = await _round_robin(tournament_id, stage_1.id, "A", 4)
        group_b = await _round_robin(tournament_id, stage_1.id, "B", 3)

        response = await send_tournament_request(
            HTTPMethod.POST,
            "stage_items/elimination_from_sources",
            auth_context,
            json={
                "stage_id": stage_2.id,
                "name": "Consolation",
                "take": "bottom",
                "sources": [
                    {"stage_item_id": group_a, "positions": 2},
                    {"stage_item_id": group_b, "positions": 2},
                ],
            },
        )

        [stage] = [
            stage
            for stage in await get_full_tournament_details(tournament_id)
            if stage.id == stage_2.id
        ]
        [bracket] = stage.stage_items
        positions_by_source = {
            group_a: sorted(
                inp.winner_position
                for inp in bracket.inputs
                if inp.winner_from_stage_item_id == group_a
            ),
            group_b: sorted(
                inp.winner_position
                for inp in bracket.inputs
                if inp.winner_from_stage_item_id == group_b
            ),
        }

        await sql_delete_stage_item_with_foreign_keys(bracket.id)
        await sql_delete_stage_item_with_foreign_keys(group_a)
        await sql_delete_stage_item_with_foreign_keys(group_b)

    assert response == {"success": True}
    assert bracket.team_count == 4  # 4 qualifiers, no byes
    assert positions_by_source == {group_a: [3, 4], group_b: [2, 3]}
