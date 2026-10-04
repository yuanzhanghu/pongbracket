"""
Extra tests for bracket/routes/tournaments.py.
Covers the 401 error branch for club access, the ranking cleanup on delete,
the logo removal error path, the get_tournaments branches (401, 404, 200
for endpoint_name lookups), and the unreachable RuntimeError branch.
"""

from collections.abc import Generator
from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

import aiohttp
import pytest

from bracket.database import database
from bracket.routes.tournaments import get_tournaments
from bracket.schema import rankings
from bracket.utils.dummy_records import DUMMY_RANKING1, DUMMY_TOURNAMENT
from bracket.utils.http import HTTPMethod
from tests.integration_tests.api.shared import (
    SUCCESS_RESPONSE,
    send_auth_request,
    send_request,
    send_tournament_request,
)
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import inserted_ranking, inserted_tournament


@pytest.mark.asyncio(loop_scope="session")
async def test_create_tournament_no_club_access(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """User has no access to the club -> 401."""
    body = {
        "name": "Some name",
        "start_time": "2024-01-01T00:00:00Z",
        "club_id": auth_context.club.id + 999,
        "dashboard_public": True,
        "dashboard_endpoint": "no-access-endpoint",
        "players_can_be_in_multiple_teams": True,
        "auto_assign_courts": True,
        "duration_minutes": 10,
        "margin_minutes": 5,
    }
    response = await send_auth_request(HTTPMethod.POST, "tournaments", auth_context, json=body)
    assert response == {"detail": "俱乐部 ID 无效"}


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_tournament_removes_rankings(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """Deleting a tournament should also delete its rankings."""
    async with inserted_tournament(
        DUMMY_TOURNAMENT.model_copy(
            update={
                "club_id": auth_context.club.id,
                "dashboard_endpoint": "to-delete",
            }
        )
    ) as tournament_inserted:
        async with inserted_ranking(
            DUMMY_RANKING1.model_copy(
                update={"tournament_id": tournament_inserted.id, "position": 1}
            )
        ) as ranking_inserted:
            assert (
                await send_tournament_request(
                    HTTPMethod.DELETE,
                    "",
                    auth_context.model_copy(update={"tournament": tournament_inserted}),
                )
                == SUCCESS_RESPONSE
            )
            rows = await database.fetch_all(
                query=rankings.select().where(rankings.c.id == ranking_inserted.id)
            )
            assert len(rows) == 0


@contextmanager
def mock_remove_fails() -> Generator[None]:
    with patch(
        "bracket.routes.tournaments.aiofiles.os.remove",
        AsyncMock(side_effect=OSError("simulated")),
    ):
        yield


@pytest.mark.asyncio(loop_scope="session")
async def test_upload_logo_removal_error(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """When removing the old logo file fails, the error is logged but the request succeeds.
    Uses a separate tournament to avoid polluting the auth_context tournament.
    """
    from bracket.utils.dummy_records import DUMMY_TOURNAMENT
    from tests.integration_tests.sql import inserted_tournament

    async with inserted_tournament(
        DUMMY_TOURNAMENT.model_copy(
            update={
                "club_id": auth_context.club.id,
                "dashboard_endpoint": "logo-test",
            }
        )
    ) as tournament_inserted:
        test_auth = auth_context.model_copy(update={"tournament": tournament_inserted})
        test_file_path = "tests/integration_tests/assets/test_logo.png"
        data = aiohttp.FormData()
        data.add_field(
            "file",
            open(test_file_path, "rb"),  # pylint: disable=consider-using-with
            filename="test_logo.png",
            content_type="image/png",
        )

        response = await send_tournament_request(
            method=HTTPMethod.POST,
            endpoint="logo",
            auth_context=test_auth,
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
                endpoint="logo",
                auth_context=test_auth,
                body=data2,
            )
        assert response2.get("data", {}).get("logo_path")
        assert response2["data"]["logo_path"] != response["data"]["logo_path"]


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_tournament_logo_removes_existing_file(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """
    delete_tournament_logo removes the on-disk logo file when:
      - the tournament has a logo_path set, AND
      - the file at static/tournament-logos/{logo_path} exists.
    This exercises line 23 (`await aiofiles.os.remove(logo_path)`).
    """
    import os
    import tempfile

    from bracket.logic.tournaments import delete_tournament_logo
    from bracket.utils.dummy_records import DUMMY_TOURNAMENT
    from tests.integration_tests.sql import inserted_tournament

    # Use a unique logo filename so we don't clash with other tests' files.
    logo_filename = "test_delete_logo_existing.png"
    full_logo_dir = "static/tournament-logos"
    os.makedirs(full_logo_dir, exist_ok=True)
    full_logo_path = os.path.join(full_logo_dir, logo_filename)

    # Ensure clean slate.
    if os.path.exists(full_logo_path):
        os.remove(full_logo_path)

    # Write a tiny dummy file at the logo path.
    with open(full_logo_path, "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n")  # PNG magic bytes

    try:
        async with inserted_tournament(
            DUMMY_TOURNAMENT.model_copy(
                update={
                    "club_id": auth_context.club.id,
                    "dashboard_endpoint": "logo-delete-test",
                    "logo_path": logo_filename,
                }
            )
        ) as tournament_inserted:
            assert os.path.exists(full_logo_path)
            await delete_tournament_logo(tournament_inserted.id)
            # File should now be gone (line 23 remove() executed successfully).
            assert not os.path.exists(full_logo_path)
    finally:
        if os.path.exists(full_logo_path):
            os.remove(full_logo_path)


@pytest.mark.asyncio(loop_scope="session")
async def test_get_tournaments_user_none_endpoint_name_none_raises() -> None:
    """Calling get_tournaments with user=None, endpoint_name=None directly
    hits the first match arm and raises the unauthorized_exception (line 81).
    This branch is unreachable via HTTP because FastAPI's OAuth2PasswordBearer
    raises 401 ("Not authenticated") before the function body runs.
    """
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await get_tournaments(user=None, endpoint_name=None)
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "你没有权限访问该比赛"


@pytest.mark.asyncio(loop_scope="session")
async def test_get_tournaments_endpoint_name_public(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """GET /tournaments?endpoint_name=X with an Authorization header (token value
    is irrelevant because the dep short-circuits on endpoint_name) and an existing
    public tournament X -> 200 with the tournament data (lines 84-91).
    """
    endpoint = "public-endpoint-extra"
    async with inserted_tournament(
        DUMMY_TOURNAMENT.model_copy(
            update={
                "club_id": auth_context.club.id,
                "dashboard_endpoint": endpoint,
                "dashboard_public": True,
            }
        )
    ):
        # Provide an Authorization header so OAuth2PasswordBearer does not
        # auto-raise "Not authenticated". The token is unused: when endpoint_name
        # is provided and the tournament exists, the dep returns None.
        response = await send_request(
            HTTPMethod.GET,
            f"tournaments?endpoint_name={endpoint}",
            headers={"Authorization": "Bearer anything"},
        )
        assert "data" in response
        assert len(response["data"]) == 1
        assert response["data"][0]["dashboard_endpoint"] == endpoint


@pytest.mark.asyncio(loop_scope="session")
async def test_get_tournaments_endpoint_name_not_found_404() -> None:
    """Calling get_tournaments with endpoint_name pointing to a non-existent
    tournament -> 404 raise (line 86). Unreachable via HTTP: the dep
    user_authenticated_or_public_dashboard_by_endpoint_name raises 401 first.
    """
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await get_tournaments(user=None, endpoint_name="definitely-not-a-real-endpoint")
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "找不到该比赛"


@pytest.mark.asyncio(loop_scope="session")
async def test_get_tournaments_unreachable_runtime_error_branch() -> None:
    """The match-statement fallback `raise RuntimeError()` is unreachable from
    HTTP because the user dependency is typed `UserPublic | None`. Call the
    function directly with a user that is neither None nor a UserPublic, and
    with endpoint_name=None, to exercise line 99.
    """
    with pytest.raises(RuntimeError):
        await get_tournaments(user="not-a-UserPublic", endpoint_name=None)  # type: ignore[arg-type]
