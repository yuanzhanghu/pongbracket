"""
Tests for bracket/routes/favorites.py and bracket/sql/favorites.py.

Covers:
- GET /me/tournaments (list followed)
- POST /me/favorites/{tid} on a viewable tournament -> success, row exists
- POST /me/favorites/{tid} on a private, non-viewable tournament -> 403
- DELETE /me/favorites/{tid} -> row removed
- sql.favorites.get_followed_tournaments: favorited + participated + scorer arms
"""

import pytest

from bracket.database import database
from bracket.sql.favorites import (
    get_followed_tournaments,
    is_favorited,
)
from bracket.sql.participants import add_scorer
from bracket.utils.dummy_records import DUMMY_CLUB, DUMMY_TEAM1, DUMMY_TOURNAMENT
from bracket.utils.http import HTTPMethod
from tests.integration_tests.api.shared import SUCCESS_RESPONSE, send_request
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import (
    inserted_club,
    inserted_team,
    inserted_tournament,
)


@pytest.mark.asyncio(loop_scope="session")
async def test_add_favorite_viewable_tournament_and_remove(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """POST /me/favorites/{tid} on a tournament the owner can view (it is under
    their own club) succeeds and persists a row; DELETE removes it (favorites.py
    37-48, 56-57; sql.favorites add_favorite line 7 and remove_favorite line 18)."""
    tournament_id = auth_context.tournament.id
    user_id = auth_context.user.id

    response = await send_request(
        HTTPMethod.POST,
        f"me/favorites/{tournament_id}",
        json={},
        headers=auth_context.headers,
    )
    assert response == SUCCESS_RESPONSE
    assert await is_favorited(user_id, tournament_id) is True

    response = await send_request(
        HTTPMethod.DELETE,
        f"me/favorites/{tournament_id}",
        headers=auth_context.headers,
    )
    assert response == SUCCESS_RESPONSE
    assert await is_favorited(user_id, tournament_id) is False


@pytest.mark.asyncio(loop_scope="session")
async def test_add_favorite_private_unviewable_tournament_403(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """POST /me/favorites/{tid} on a private tournament under a DIFFERENT club
    (so the user is neither a member, nor bound, nor is it public) -> 403
    (favorites.py 43-46)."""
    async with inserted_club(DUMMY_CLUB) as other_club:
        async with inserted_tournament(
            DUMMY_TOURNAMENT.model_copy(
                update={
                    "club_id": other_club.id,
                    "dashboard_endpoint": "gapsapi-private",
                    "dashboard_public": False,
                }
            )
        ) as private_tournament:
            response = await send_request(
                HTTPMethod.POST,
                f"me/favorites/{private_tournament.id}",
                json={},
                headers=auth_context.headers,
            )
            assert response == {"detail": "无法关注你无权查看的比赛"}
            assert await is_favorited(auth_context.user.id, private_tournament.id) is False


@pytest.mark.asyncio(loop_scope="session")
async def test_list_followed_tournaments_endpoint(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """GET /me/tournaments returns favorited tournaments (favorites.py line 26).
    After favoriting the auth tournament, it appears in the list."""
    tournament_id = auth_context.tournament.id
    try:
        post = await send_request(
            HTTPMethod.POST,
            f"me/favorites/{tournament_id}",
            json={},
            headers=auth_context.headers,
        )
        assert post == SUCCESS_RESPONSE

        response = await send_request(
            HTTPMethod.GET, "me/tournaments", headers=auth_context.headers
        )
        assert "data" in response
        ids = {row["id"] for row in response["data"]}
        assert tournament_id in ids
    finally:
        await database.execute(
            "DELETE FROM tournament_favorites WHERE user_id = :u AND tournament_id = :t",
            {"u": auth_context.user.id, "t": tournament_id},
        )


@pytest.mark.asyncio(loop_scope="session")
async def test_get_followed_tournaments_all_arms(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """get_followed_tournaments returns tournaments reached via each arm:
    explicitly favorited, participated (teams_x_users), and scorer
    (tournament_scorers) (sql.favorites.py 36-47)."""
    user_id = auth_context.user.id
    club_id = auth_context.club.id

    async with (
        inserted_tournament(
            DUMMY_TOURNAMENT.model_copy(
                update={"club_id": club_id, "dashboard_endpoint": "gapsapi-fav"}
            )
        ) as fav_tournament,
        inserted_tournament(
            DUMMY_TOURNAMENT.model_copy(
                update={"club_id": club_id, "dashboard_endpoint": "gapsapi-part"}
            )
        ) as part_tournament,
        inserted_tournament(
            DUMMY_TOURNAMENT.model_copy(
                update={"club_id": club_id, "dashboard_endpoint": "gapsapi-score"}
            )
        ) as score_tournament,
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": part_tournament.id})
        ) as team_inserted,
    ):
        # Favorited arm.
        await database.execute(
            "INSERT INTO tournament_favorites (user_id, tournament_id) VALUES (:u, :t)",
            {"u": user_id, "t": fav_tournament.id},
        )
        # Participated arm: bind the user to a team in part_tournament.
        await database.execute(
            "INSERT INTO teams_x_users (team_id, user_id, tournament_id) VALUES (:tm, :u, :t)",
            {"tm": team_inserted.id, "u": user_id, "t": part_tournament.id},
        )
        # Scorer arm.
        await add_scorer(score_tournament.id, user_id)

        try:
            followed = await get_followed_tournaments(user_id)
            followed_ids = {t.id for t in followed}
            assert fav_tournament.id in followed_ids
            assert part_tournament.id in followed_ids
            assert score_tournament.id in followed_ids
        finally:
            await database.execute(
                "DELETE FROM tournament_favorites WHERE user_id = :u AND tournament_id = :t",
                {"u": user_id, "t": fav_tournament.id},
            )
            await database.execute(
                "DELETE FROM teams_x_users WHERE user_id = :u AND tournament_id = :t",
                {"u": user_id, "t": part_tournament.id},
            )
            await database.execute(
                "DELETE FROM tournament_scorers WHERE user_id = :u AND tournament_id = :t",
                {"u": user_id, "t": score_tournament.id},
            )
