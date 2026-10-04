import pytest

from bracket.sql.shared import sql_delete_stage_item_with_foreign_keys
from bracket.sql.stages import get_full_tournament_details
from bracket.utils.dummy_records import DUMMY_STAGE1, DUMMY_TEAM1
from bracket.utils.http import HTTPMethod
from tests.integration_tests.api.shared import send_tournament_request
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import inserted_stage, inserted_team


@pytest.mark.asyncio(loop_scope="session")
async def test_create_round_robin_groups_distributes_by_seeding(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    tournament_id = auth_context.tournament.id
    async with (
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": tournament_id})
        ) as stage_inserted,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as team_1,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as team_2,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as team_3,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as team_4,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as team_5,
    ):
        # team_count is the TOTAL: 5 teams split across 2 groups -> sizes [3, 2].
        response = await send_tournament_request(
            HTTPMethod.POST,
            "stage_items/round_robin_groups",
            auth_context,
            json={"stage_id": stage_inserted.id, "group_count": 2, "team_count": 5},
        )

        [stage] = [
            stage
            for stage in await get_full_tournament_details(tournament_id)
            if stage.id == stage_inserted.id
        ]
        groups = sorted(stage.stage_items, key=lambda si: si.name)
        names = [g.name for g in groups]
        team_counts = [g.team_count for g in groups]
        team_ids_per_group = [
            {inp.team_id for inp in g.inputs if inp.team_id is not None} for g in groups
        ]

        for group in groups:
            await sql_delete_stage_item_with_foreign_keys(group.id)

    assert response == {"success": True}
    assert names == ["小组1", "小组2"]
    assert team_counts == [3, 2]
    # Snake seeding of 5 teams over groups of [3, 2] -> [1, 4, 5] and [2, 3].
    assert team_ids_per_group[0] == {team_1.id, team_4.id, team_5.id}
    assert team_ids_per_group[1] == {team_2.id, team_3.id}


@pytest.mark.asyncio(loop_scope="session")
async def test_create_round_robin_groups_block_distributes_sequentially(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    tournament_id = auth_context.tournament.id
    async with (
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": tournament_id})
        ) as stage_inserted,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as team_1,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as team_2,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as team_3,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as team_4,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as team_5,
    ):
        # Block method: 5 teams over 2 groups -> sizes [3, 2] filled with consecutive seeds.
        response = await send_tournament_request(
            HTTPMethod.POST,
            "stage_items/round_robin_groups",
            auth_context,
            json={
                "stage_id": stage_inserted.id,
                "group_count": 2,
                "team_count": 5,
                "method": "block",
            },
        )

        [stage] = [
            stage
            for stage in await get_full_tournament_details(tournament_id)
            if stage.id == stage_inserted.id
        ]
        groups = sorted(stage.stage_items, key=lambda si: si.name)
        team_ids_per_group = [
            {inp.team_id for inp in g.inputs if inp.team_id is not None} for g in groups
        ]

        for group in groups:
            await sql_delete_stage_item_with_foreign_keys(group.id)

    assert response == {"success": True}
    # Consecutive seeds stay together: [1, 2, 3] and [4, 5].
    assert team_ids_per_group[0] == {team_1.id, team_2.id, team_3.id}
    assert team_ids_per_group[1] == {team_4.id, team_5.id}


@pytest.mark.asyncio(loop_scope="session")
async def test_create_round_robin_groups_leaves_empty_slots(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    tournament_id = auth_context.tournament.id
    async with (
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": tournament_id})
        ) as stage_inserted,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})),
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})),
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})),
    ):
        # total_team_count 6 over 2 groups -> [3, 3] = 6 slots, but only 3 active teams.
        response = await send_tournament_request(
            HTTPMethod.POST,
            "stage_items/round_robin_groups",
            auth_context,
            json={"stage_id": stage_inserted.id, "group_count": 2, "team_count": 6},
        )

        [stage] = [
            stage
            for stage in await get_full_tournament_details(tournament_id)
            if stage.id == stage_inserted.id
        ]
        groups = list(stage.stage_items)
        assigned = sum(1 for g in groups for inp in g.inputs if inp.team_id is not None)

        for group in groups:
            await sql_delete_stage_item_with_foreign_keys(group.id)

    assert response == {"success": True}
    assert len(groups) == 2
    assert assigned == 3
