import aiofiles.os
import aiohttp
import pytest

from bracket.database import database
from bracket.models.db.team import Team
from bracket.schema import players, players_x_teams, teams
from bracket.utils.db import fetch_one_parsed_certain
from bracket.utils.dummy_records import DUMMY_MOCK_TIME, DUMMY_PLAYER1, DUMMY_TEAM1
from bracket.utils.http import HTTPMethod
from tests.integration_tests.api.shared import SUCCESS_RESPONSE, send_tournament_request
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import (
    assert_row_count_and_clear,
    inserted_player,
    inserted_team,
)


@pytest.mark.asyncio(loop_scope="session")
async def test_teams_endpoint(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with inserted_team(
        DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
    ) as team_inserted:
        assert await send_tournament_request(HTTPMethod.GET, "teams", auth_context, {}) == {
            "data": {
                "teams": [
                    {
                        "active": True,
                        "created": DUMMY_MOCK_TIME.isoformat().replace("+00:00", "Z"),
                        "id": team_inserted.id,
                        "name": "Team 1",
                        "players": [],
                        "tournament_id": team_inserted.tournament_id,
                        "elo_score": "1200.0",
                        "wins": 0,
                        "draws": 0,
                        "losses": 0,
                        "logo_path": None,
                        "bound_user_id": None,
                        "rating": None,
                        "rating_status": None,
                        "settled_pre_rating": None,
                        "settled_post_rating": None,
                        "sort_order": 0,
                    }
                ],
                "count": 1,
            },
        }


@pytest.mark.asyncio(loop_scope="session")
async def test_teams_endpoint_sort_by_rating(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    tournament_id = auth_context.tournament.id
    async with (
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as team_1,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as team_2,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as team_3,
    ):
        # sort_by=rating is accepted; with no ratings set, teams fall back to creation order.
        response = await send_tournament_request(
            HTTPMethod.GET, "teams?sort_by=rating&sort_direction=desc", auth_context, {}
        )
        returned_ids = [team["id"] for team in response["data"]["teams"]]
        assert returned_ids == [team_1.id, team_2.id, team_3.id]


@pytest.mark.asyncio(loop_scope="session")
async def test_move_team_up_swaps_sort_order(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    tournament_id = auth_context.tournament.id
    async with (
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id, "sort_order": 1})
        ) as team_1,
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id, "sort_order": 2})
        ) as team_2,
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id, "sort_order": 3})
        ) as team_3,
    ):
        # Move the last team up one slot -> it swaps places with team_2.
        response = await send_tournament_request(
            HTTPMethod.POST, f"teams/{team_3.id}/move", auth_context, json={"direction": "up"}
        )
        ordered = await send_tournament_request(
            HTTPMethod.GET, "teams?sort_by=sort_order&sort_direction=asc", auth_context, {}
        )
        ids = [team["id"] for team in ordered["data"]["teams"]]

    assert response == {"success": True}
    assert ids == [team_1.id, team_3.id, team_2.id]


@pytest.mark.asyncio(loop_scope="session")
async def test_move_team_at_boundary_is_noop(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    tournament_id = auth_context.tournament.id
    async with (
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id, "sort_order": 1})
        ) as team_1,
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id, "sort_order": 2})
        ) as team_2,
    ):
        # Moving the last team down has no neighbor -> order is unchanged.
        response = await send_tournament_request(
            HTTPMethod.POST, f"teams/{team_2.id}/move", auth_context, json={"direction": "down"}
        )
        ordered = await send_tournament_request(
            HTTPMethod.GET, "teams?sort_by=sort_order&sort_direction=asc", auth_context, {}
        )
        ids = [team["id"] for team in ordered["data"]["teams"]]

    assert response == {"success": True}
    assert ids == [team_1.id, team_2.id]


@pytest.mark.asyncio(loop_scope="session")
async def test_move_team_with_tied_sort_order(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """Legacy rows share sort_order 0. A move must still shift the team exactly one
    position in the displayed (sort_order, id) order, not jump past every tied row."""
    tournament_id = auth_context.tournament.id
    async with (
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id, "sort_order": 0})
        ) as team_1,
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id, "sort_order": 0})
        ) as team_2,
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id, "sort_order": 0})
        ) as team_3,
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id, "sort_order": 1})
        ) as team_4,
    ):
        # Displayed order is [1, 2, 3, 4]; moving the first team down must land it in
        # second place, not at the end next to the only row with a bigger sort_order.
        await send_tournament_request(
            HTTPMethod.POST, f"teams/{team_1.id}/move", auth_context, json={"direction": "down"}
        )
        ordered = await send_tournament_request(
            HTTPMethod.GET, "teams?sort_by=sort_order&sort_direction=asc", auth_context, {}
        )
        ids = [team["id"] for team in ordered["data"]["teams"]]

    assert ids == [team_2.id, team_1.id, team_3.id, team_4.id]


@pytest.mark.asyncio(loop_scope="session")
async def test_create_team_assigns_incrementing_sort_order(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    first = await send_tournament_request(
        HTTPMethod.POST,
        "teams",
        auth_context,
        None,
        {"name": "First", "active": True, "player_names": []},
    )
    second = await send_tournament_request(
        HTTPMethod.POST,
        "teams",
        auth_context,
        None,
        {"name": "Second", "active": True, "player_names": []},
    )
    assert second["data"]["sort_order"] > first["data"]["sort_order"]
    await assert_row_count_and_clear(teams, 2)


@pytest.mark.asyncio(loop_scope="session")
async def test_create_team(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    body = {"name": "Some new name", "active": True, "player_names": []}
    response = await send_tournament_request(HTTPMethod.POST, "teams", auth_context, None, body)
    assert response["data"]["name"] == body["name"]
    await assert_row_count_and_clear(teams, 1)


@pytest.mark.asyncio(loop_scope="session")
async def test_create_teams(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    body = {"names": "Team -1,Player 42,Player 43\nTeam -2,", "active": True}
    response = await send_tournament_request(
        HTTPMethod.POST, "teams_multi", auth_context, None, body
    )
    assert response["success"] is True

    # The players from the CSV must end up linked to their team, not floating free.
    teams_response = await send_tournament_request(HTTPMethod.GET, "teams", auth_context, {})
    members_per_team = {
        team["name"]: sorted(player["name"] for player in team["players"])
        for team in teams_response["data"]["teams"]
    }
    assert members_per_team == {"Team -1": ["Player 42", "Player 43"], "Team -2": []}

    await assert_row_count_and_clear(teams, 2)
    await assert_row_count_and_clear(players, 2)


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_team(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with inserted_team(
        DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
    ) as team_inserted:
        assert (
            await send_tournament_request(
                HTTPMethod.DELETE, f"teams/{team_inserted.id}", auth_context, {}
            )
            == SUCCESS_RESPONSE
        )
        await assert_row_count_and_clear(teams, 0)


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_team_deletes_its_members(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    # Members exist only through their team, so deleting the team must not leave
    # orphaned player rows behind — nothing in the UI could ever remove them.
    body = {"name": "Team with members", "active": True, "player_names": ["Player A", "Player B"]}
    create_response = await send_tournament_request(
        HTTPMethod.POST, "teams", auth_context, None, body
    )
    team_id = create_response["data"]["id"]

    assert (
        await send_tournament_request(HTTPMethod.DELETE, f"teams/{team_id}", auth_context, {})
        == SUCCESS_RESPONSE
    )
    assert await database.fetch_all(query=players.select()) == []

    await assert_row_count_and_clear(players, 0)
    await assert_row_count_and_clear(teams, 0)


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_team_keeps_members_of_other_teams(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    # A player shared with another team survives the deletion.
    async with (
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as team_a,
        inserted_team(
            DUMMY_TEAM1.model_copy(
                update={"tournament_id": auth_context.tournament.id, "name": "Other team"}
            )
        ) as team_b,
        inserted_player(
            DUMMY_PLAYER1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as player_inserted,
    ):
        for team_id in (team_a.id, team_b.id):
            await database.execute(
                query=players_x_teams.insert(),
                values={"team_id": team_id, "player_id": player_inserted.id},
            )

        assert (
            await send_tournament_request(HTTPMethod.DELETE, f"teams/{team_a.id}", auth_context, {})
            == SUCCESS_RESPONSE
        )
        remaining = await database.fetch_all(query=players.select())
        assert [player["id"] for player in remaining] == [player_inserted.id]

    await assert_row_count_and_clear(players, 0)
    await assert_row_count_and_clear(teams, 0)


@pytest.mark.asyncio(loop_scope="session")
async def test_update_team(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    body = {"name": "Some new name", "active": True, "player_names": []}
    async with inserted_team(
        DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
    ) as team_inserted:
        response = await send_tournament_request(
            HTTPMethod.PUT, f"teams/{team_inserted.id}", auth_context, None, body
        )
        updated_team = await fetch_one_parsed_certain(
            database, Team, query=teams.select().where(teams.c.id == team_inserted.id)
        )
        assert updated_team.name == body["name"]
        assert response["data"]["name"] == body["name"]

        await assert_row_count_and_clear(teams, 1)


@pytest.mark.asyncio(loop_scope="session")
async def test_create_team_duplicate_name_rejected(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with inserted_team(
        DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
    ) as team_inserted:
        body = {"name": team_inserted.name, "active": True, "player_names": []}
        response = await send_tournament_request(HTTPMethod.POST, "teams", auth_context, None, body)
        assert response == {"detail": f"队伍名“{team_inserted.name}”已存在"}
        await assert_row_count_and_clear(teams, 1)


@pytest.mark.asyncio(loop_scope="session")
async def test_update_team_duplicate_name_rejected(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with inserted_team(
        DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
    ) as team1:
        async with inserted_team(
            DUMMY_TEAM1.model_copy(
                update={"tournament_id": auth_context.tournament.id, "name": "Other team"}
            )
        ) as team2:
            body = {"name": team1.name, "active": True}
            response = await send_tournament_request(
                HTTPMethod.PUT, f"teams/{team2.id}", auth_context, None, body
            )
            assert response == {"detail": f"队伍名“{team1.name}”已存在"}

            # Saving a team under its own name is still allowed.
            body = {"name": team2.name, "active": True}
            response = await send_tournament_request(
                HTTPMethod.PUT, f"teams/{team2.id}", auth_context, None, body
            )
            assert response["data"]["name"] == team2.name


@pytest.mark.asyncio(loop_scope="session")
async def test_update_team_player_names_sync(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with inserted_team(
        DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
    ) as team_inserted:
        # New names create players and link them to the team.
        body = {"name": "Some new name", "active": True, "player_names": ["Player A", "Player B"]}
        response = await send_tournament_request(
            HTTPMethod.PUT, f"teams/{team_inserted.id}", auth_context, None, body
        )
        assert response["data"]["name"] == body["name"]
        teams_response = await send_tournament_request(HTTPMethod.GET, "teams", auth_context, {})
        member_names = sorted(
            player["name"] for player in teams_response["data"]["teams"][0]["players"]
        )
        assert member_names == ["Player A", "Player B"]

        # Removing a name from the list unlinks and deletes the orphaned player.
        body = {"name": "Some new name", "active": True, "player_names": ["Player B"]}
        await send_tournament_request(
            HTTPMethod.PUT, f"teams/{team_inserted.id}", auth_context, None, body
        )
        teams_response = await send_tournament_request(HTTPMethod.GET, "teams", auth_context, {})
        member_names = [player["name"] for player in teams_response["data"]["teams"][0]["players"]]
        assert member_names == ["Player B"]

        # Omitting player_names leaves the members untouched.
        body = {"name": "Some new name", "active": True}
        await send_tournament_request(
            HTTPMethod.PUT, f"teams/{team_inserted.id}", auth_context, None, body
        )
        teams_response = await send_tournament_request(HTTPMethod.GET, "teams", auth_context, {})
        member_names = [player["name"] for player in teams_response["data"]["teams"][0]["players"]]
        assert member_names == ["Player B"]

        await assert_row_count_and_clear(players, 1)
        await assert_row_count_and_clear(teams, 1)


@pytest.mark.asyncio(loop_scope="session")
async def test_team_upload_and_remove_logo(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    test_file_path = "tests/integration_tests/assets/test_logo.png"
    data = aiohttp.FormData()
    data.add_field(
        "file",
        open(test_file_path, "rb"),  # pylint: disable=consider-using-with
        filename="test_logo.png",
        content_type="image/png",
    )

    async with inserted_team(
        DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
    ) as team_inserted:
        response = await send_tournament_request(
            method=HTTPMethod.POST,
            endpoint=f"teams/{team_inserted.id}/logo",
            auth_context=auth_context,
            body=data,
        )

        assert response["data"]["logo_path"], f"Response: {response}"
        assert await aiofiles.os.path.exists(f"static/team-logos/{response['data']['logo_path']}")

        response = await send_tournament_request(
            method=HTTPMethod.POST,
            endpoint="logo",
            auth_context=auth_context,
            body=aiohttp.FormData(),
        )

        assert response["data"]["logo_path"] is None, f"Response: {response}"
        assert not await aiofiles.os.path.exists(
            f"static/team-logos/{response['data']['logo_path']}"
        )
