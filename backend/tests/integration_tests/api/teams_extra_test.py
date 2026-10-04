"""
Extra tests for bracket/routes/teams.py.
Covers adding a new player to a team and the logo removal error path.
"""

from collections.abc import Generator
from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

import aiohttp
import pytest

from bracket.utils.dummy_records import DUMMY_PLAYER1, DUMMY_TEAM1
from bracket.utils.http import HTTPMethod
from tests.integration_tests.api.shared import send_tournament_request
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import inserted_player_in_team, inserted_team


@pytest.mark.asyncio(loop_scope="session")
async def test_update_team_adds_new_member(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """Updating a team with a new name in player_names should add that player."""
    async with inserted_team(
        DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
    ) as team_inserted:
        async with inserted_player_in_team(
            DUMMY_PLAYER1.model_copy(update={"tournament_id": auth_context.tournament.id}),
            team_id=team_inserted.id,
        ) as player1:
            body = {
                "name": "Updated Team",
                "active": True,
                "player_names": [player1.name, "New Player"],
            }
            response = await send_tournament_request(
                HTTPMethod.PUT,
                f"teams/{team_inserted.id}",
                auth_context,
                None,
                body,
            )
            assert response.get("success") is True or "data" in response

            teams_response = await send_tournament_request(
                HTTPMethod.GET, "teams", auth_context, {}
            )
            member_names = sorted(
                player["name"] for player in teams_response["data"]["teams"][0]["players"]
            )
            assert member_names == sorted([player1.name, "New Player"])

            # Remove the API-created player again so later tests see a clean table.
            await send_tournament_request(
                HTTPMethod.PUT,
                f"teams/{team_inserted.id}",
                auth_context,
                None,
                {"name": "Updated Team", "active": True, "player_names": [player1.name]},
            )


@contextmanager
def mock_remove_fails() -> Generator[None]:
    with patch(
        "bracket.routes.teams.aiofiles.os.remove",
        AsyncMock(side_effect=OSError("simulated")),
    ):
        yield


@pytest.mark.asyncio(loop_scope="session")
async def test_update_team_logo_removal_error(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """When removing the old logo file fails, the error is logged but the request succeeds."""
    test_file_path = "tests/integration_tests/assets/test_logo.png"

    async with inserted_team(
        DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
    ) as team_inserted:
        data = aiohttp.FormData()
        data.add_field(
            "file",
            open(test_file_path, "rb"),  # pylint: disable=consider-using-with
            filename="test_logo.png",
            content_type="image/png",
        )
        response = await send_tournament_request(
            method=HTTPMethod.POST,
            endpoint=f"teams/{team_inserted.id}/logo",
            auth_context=auth_context,
            body=data,
        )
        assert response.get("data", {}).get("logo_path")

        data2 = aiohttp.FormData()
        data2.add_field(
            "file",
            open(test_file_path, "rb"),  # pylint: disable=consider-using-with
            filename="test_logo2.png",
            content_type="image/png",
        )
        with mock_remove_fails():
            response2 = await send_tournament_request(
                method=HTTPMethod.POST,
                endpoint=f"teams/{team_inserted.id}/logo",
                auth_context=auth_context,
                body=data2,
            )
        assert response2.get("data", {}).get("logo_path")
