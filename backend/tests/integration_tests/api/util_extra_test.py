"""
Extra tests for bracket/routes/util.py dependency functions.
Covers the 404/400 error branches that are not exercised by the main route tests.
"""

import pytest

from bracket.models.db.tournament import TournamentStatus
from bracket.utils.dummy_records import DUMMY_TOURNAMENT
from bracket.utils.http import HTTPMethod
from tests.integration_tests.api.shared import send_tournament_request
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import inserted_tournament


@pytest.mark.asyncio(loop_scope="session")
async def test_round_dependency_404(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    response = await send_tournament_request(
        HTTPMethod.PUT, "rounds/-1", auth_context, json={"name": "x", "is_draft": True}
    )
    assert response == {"detail": "找不到 ID 为 -1 的回合"}


@pytest.mark.asyncio(loop_scope="session")
async def test_stage_dependency_404(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    response = await send_tournament_request(
        HTTPMethod.PUT, "stages/-1", auth_context, json={"name": "x"}
    )
    assert response == {"detail": "找不到 ID 为 -1 的阶段"}


@pytest.mark.asyncio(loop_scope="session")
async def test_match_dependency_404(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    response = await send_tournament_request(HTTPMethod.PUT, "matches/-1", auth_context, json={})
    assert response == {"detail": "找不到 ID 为 -1 的对阵"}


@pytest.mark.asyncio(loop_scope="session")
async def test_team_dependency_404(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    response = await send_tournament_request(
        HTTPMethod.PUT,
        "teams/-1",
        auth_context,
        json={"name": "x", "active": True, "player_names": []},
    )
    assert response == {"detail": "找不到 ID 为 -1 的队伍"}


@pytest.mark.asyncio(loop_scope="session")
async def test_team_with_players_dependency_404(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    response = await send_tournament_request(HTTPMethod.DELETE, "teams/-1", auth_context, {})
    assert response == {"detail": "找不到 ID 为 -1 的队伍"}


@pytest.mark.asyncio(loop_scope="session")
async def test_disallow_archived_tournament_400(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    # Create a separate archived tournament (auth_context tournament stays open)
    async with inserted_tournament(
        DUMMY_TOURNAMENT.model_copy(
            update={
                "club_id": auth_context.club.id,
                "dashboard_endpoint": None,
                "status": TournamentStatus.ARCHIVED,
            }
        )
    ) as archived_tournament:
        response = await send_tournament_request(
            HTTPMethod.PUT,
            "",
            auth_context.model_copy(update={"tournament": archived_tournament}),
            json={"name": "x"},
        )
        assert response == {"detail": "已归档的比赛不能修改"}
