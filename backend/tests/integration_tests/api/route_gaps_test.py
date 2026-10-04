"""
Small route/SQL coverage gaps for matches, rounds, sql/rounds, stage_items,
tournaments, util and auth.

Each test crafts the minimal request (or direct call, where the branch is
unreachable over HTTP) needed to drive a specific missing line.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
from heliclockter import datetime_utc

from bracket.database import database
from bracket.models.db.account import UserAccountType
from bracket.models.db.round import RoundCreateBody
from bracket.models.db.stage_item import StageType
from bracket.models.db.user import UserInsertable
from bracket.utils.dummy_records import DUMMY_STAGE1, DUMMY_STAGE_ITEM1
from bracket.utils.http import HTTPMethod
from tests.integration_tests.api.shared import send_request
from tests.integration_tests.mocks import get_mock_token
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import (
    inserted_stage,
    inserted_stage_item,
    inserted_user,
)


async def _insert(query: str, values: dict) -> int:
    return await database.fetch_val(query + " RETURNING id", values)


@asynccontextmanager
async def rated_individual_tournament(
    club_id: int,
    *,
    endpoint: str,
    settled: bool = False,
    with_unrated_participant: bool = False,
    with_match: bool = False,
) -> AsyncIterator[dict]:
    """Build a rated individual tournament (fields that are not on
    TournamentInsertable) plus optional bound participant / match, with FK-safe
    teardown. Built under ``club_id`` so the auth_context owner has access."""
    now = datetime_utc.now()
    ids: dict = {"club": club_id}
    try:
        ids["category"] = await _insert(
            "INSERT INTO rating_categories (key, name, algorithm) VALUES (:k, :n, 'chinatt')",
            {"k": f"GAPSAPI_{endpoint}", "n": "Gaps Category"},
        )
        settled_cols = ", settled_seq, settled_at" if settled else ""
        settled_vals = ", 1, :now" if settled else ""
        ids["tournament"] = await _insert(
            f"""
            INSERT INTO tournaments
                (name, start_time, club_id, dashboard_public, dashboard_endpoint,
                 is_individual, rating_category_id{settled_cols})
            VALUES ('T', :now, :club, true, :ep, true, :cat{settled_vals})
            """,
            {"now": now, "club": club_id, "ep": endpoint, "cat": ids["category"]},
        )
        ids["ranking"] = await _insert(
            "INSERT INTO rankings "
            "(tournament_id, position, win_points, draw_points, loss_points, add_score_points) "
            "VALUES (:t, 0, 1, 0.5, 0, true)",
            {"t": ids["tournament"]},
        )
        ids["stage"] = await _insert(
            "INSERT INTO stages (name, tournament_id, is_active) VALUES ('S', :t, true)",
            {"t": ids["tournament"]},
        )
        ids["stage_item"] = await _insert(
            "INSERT INTO stage_items (name, stage_id, team_count, ranking_id, type) "
            "VALUES ('SI', :s, 2, :r, 'ROUND_ROBIN')",
            {"s": ids["stage"], "r": ids["ranking"]},
        )

        if with_unrated_participant:
            ids["user"] = await _insert(
                "INSERT INTO users (email, name, password_hash, account_type) "
                "VALUES (:e, 'Unrated', 'x', 'REGULAR')",
                {"e": f"gapsapi_{endpoint}@test"},
            )
            ids["team"] = await _insert(
                "INSERT INTO teams (name, tournament_id) VALUES ('TM', :t)",
                {"t": ids["tournament"]},
            )
            # Bound participant with NO player_ratings row -> unrated.
            await database.execute(
                "INSERT INTO teams_x_users (team_id, user_id, tournament_id) VALUES (:tm, :u, :t)",
                {"tm": ids["team"], "u": ids["user"], "t": ids["tournament"]},
            )

        if with_match:
            ids["round"] = await _insert(
                "INSERT INTO rounds (name, is_draft, stage_item_id) VALUES ('R', false, :si)",
                {"si": ids["stage_item"]},
            )
            ids["input1"] = await _insert(
                "INSERT INTO stage_item_inputs (slot, tournament_id, stage_item_id, team_id) "
                "VALUES (0, :t, :si, NULL)",
                {"t": ids["tournament"], "si": ids["stage_item"]},
            )
            ids["input2"] = await _insert(
                "INSERT INTO stage_item_inputs (slot, tournament_id, stage_item_id, team_id) "
                "VALUES (1, :t, :si, NULL)",
                {"t": ids["tournament"], "si": ids["stage_item"]},
            )
            ids["match"] = await _insert(
                """
                INSERT INTO matches
                    (round_id, stage_item_input1_id, stage_item_input2_id,
                     stage_item_input1_conflict, stage_item_input2_conflict,
                     stage_item_input1_score, stage_item_input2_score,
                     duration_minutes, margin_minutes)
                VALUES (:r, :i1, :i2, false, false, 0, 0, 10, 5)
                """,
                {"r": ids["round"], "i1": ids["input1"], "i2": ids["input2"]},
            )
        yield ids
    finally:
        for table, col, key in [
            ("matches", "round_id", "round"),
            ("stage_item_inputs", "stage_item_id", "stage_item"),
            ("rounds", "id", "round"),
            ("teams_x_users", "tournament_id", "tournament"),
            ("teams", "tournament_id", "tournament"),
            ("stage_items", "id", "stage_item"),
            ("stages", "id", "stage"),
            ("rankings", "tournament_id", "tournament"),
            ("tournaments", "id", "tournament"),
            ("users", "id", "user"),
            ("rating_categories", "id", "category"),
        ]:
            if key in ids:
                await database.execute(f"DELETE FROM {table} WHERE {col} = :v", {"v": ids[key]})


# --------------------------------------------------------------------------- #
# matches.py
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio(loop_scope="session")
async def test_update_match_on_settled_tournament_400(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """PUT a match in a settled tournament -> 400 'scores are frozen'
    (matches.py line 80)."""
    async with rated_individual_tournament(
        auth_context.club.id, endpoint="settled_match", settled=True, with_match=True
    ) as ids:
        body = {
            "stage_item_input1_score": 11,
            "stage_item_input2_score": 9,
            "round_id": ids["round"],
            "court_id": None,
        }
        response = await send_request(
            HTTPMethod.PUT,
            f"tournaments/{ids['tournament']}/matches/{ids['match']}",
            json=body,
            headers=auth_context.headers,
        )
        assert response == {"detail": "赛事已结算，比分已冻结"}


@pytest.mark.asyncio(loop_scope="session")
async def test_update_match_rated_individual_draw_400(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """PUT a decided-but-tied (non 0-0) score on a rated individual tournament
    -> 400 'no draws' (matches.py 88-90)."""
    async with rated_individual_tournament(
        auth_context.club.id, endpoint="draw_match", with_match=True
    ) as ids:
        body = {
            "stage_item_input1_score": 7,
            "stage_item_input2_score": 7,
            "round_id": ids["round"],
            "court_id": None,
        }
        response = await send_request(
            HTTPMethod.PUT,
            f"tournaments/{ids['tournament']}/matches/{ids['match']}",
            json=body,
            headers=auth_context.headers,
        )
        assert response == {"detail": "乒乓球没有平局，请录入分出胜负的比分"}


# --------------------------------------------------------------------------- #
# rounds.py 86-96 + sql/rounds.py 82-97
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio(loop_scope="session")
async def test_create_round_success_path(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """Drive the create_round success path (rounds.py 86-96) plus
    set_round_active_or_draft (sql/rounds.py 82-97). No stage type currently
    advertises dynamic rounds, so we patch the property to True and call the
    handler directly."""
    from bracket.routes.rounds import create_round

    async with (
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as stage_inserted,
        inserted_stage_item(
            DUMMY_STAGE_ITEM1.model_copy(
                update={
                    "stage_id": stage_inserted.id,
                    "ranking_id": auth_context.ranking.id,
                    "type": StageType.ROUND_ROBIN,
                }
            )
        ) as stage_item_inserted,
    ):
        with patch.object(
            StageType,
            "supports_dynamic_number_of_rounds",
            property(lambda self: True),
        ):
            response = await create_round(
                tournament_id=auth_context.tournament.id,
                round_body=RoundCreateBody(stage_item_id=stage_item_inserted.id),
                user=auth_context.user,  # type: ignore[arg-type]
                _=auth_context.tournament,  # type: ignore[arg-type]
            )
        assert response.success is True

        # A draft round now exists for this stage_item (set_round_active_or_draft ran).
        drafts = await database.fetch_all(
            "SELECT id FROM rounds WHERE stage_item_id = :si AND is_draft = true",
            {"si": stage_item_inserted.id},
        )
        assert len(drafts) >= 1
        # Clean up the round we created (the context managers don't know about it).
        await database.execute(
            "DELETE FROM rounds WHERE stage_item_id = :si", {"si": stage_item_inserted.id}
        )


# --------------------------------------------------------------------------- #
# stage_items.py 55-59  (_block_start_until_all_rated)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio(loop_scope="session")
async def test_create_stage_item_blocked_unrated_participants(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """Creating a stage_item on a rated individual tournament with an unrated
    bound participant -> 400 (stage_items.py 55-59)."""
    async with rated_individual_tournament(
        auth_context.club.id, endpoint="unrated", with_unrated_participant=True
    ) as ids:
        body = {
            "name": "Group X",
            "type": StageType.ROUND_ROBIN.value,
            "team_count": 2,
            "ranking_id": ids["ranking"],
            "stage_id": ids["stage"],
        }
        response = await send_request(
            HTTPMethod.POST,
            f"tournaments/{ids['tournament']}/stage_items",
            json=body,
            headers=auth_context.headers,
        )
        assert "无法开始比赛" in response["detail"]


# --------------------------------------------------------------------------- #
# tournaments.py 182-188
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio(loop_scope="session")
async def test_create_tournament_rated_non_individual_400(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """rating_category_id set but is_individual=False -> 400 (tournaments.py 182-185)."""
    body = {
        "name": "Rated Team Tournament",
        "start_time": "2024-01-01T00:00:00Z",
        "club_id": auth_context.club.id,
        "dashboard_public": True,
        "dashboard_endpoint": "gapsapi-rated-team",
        "players_can_be_in_multiple_teams": True,
        "auto_assign_courts": True,
        "duration_minutes": 10,
        "margin_minutes": 5,
        "is_individual": False,
        "rating_category_id": 1,
    }
    response = await send_request(
        HTTPMethod.POST, "tournaments", json=body, headers=auth_context.headers
    )
    assert response == {"detail": "只有个人赛可以参与积分"}


@pytest.mark.asyncio(loop_scope="session")
async def test_create_tournament_rating_category_not_found_404(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """is_individual=True but rating_category_id doesn't exist -> 404
    (tournaments.py 187-188)."""
    body = {
        "name": "Rated Individual Tournament",
        "start_time": "2024-01-01T00:00:00Z",
        "club_id": auth_context.club.id,
        "dashboard_public": True,
        "dashboard_endpoint": "gapsapi-rated-missing",
        "players_can_be_in_multiple_teams": True,
        "auto_assign_courts": True,
        "duration_minutes": 10,
        "margin_minutes": 5,
        "is_individual": True,
        "rating_category_id": 999999999,
    }
    response = await send_request(
        HTTPMethod.POST, "tournaments", json=body, headers=auth_context.headers
    )
    assert response == {"detail": "找不到该积分类别"}


# --------------------------------------------------------------------------- #
# util.py 140 (disallow_settled_tournament) and 163 (disallow_rated_individual)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_settled_tournament_blocked(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """DELETE /tournaments/{id} on a settled tournament -> 400 (util.py 140).
    The DELETE route depends on disallow_settled_tournament; the PUT route does
    not."""
    async with rated_individual_tournament(
        auth_context.club.id, endpoint="settled_del", settled=True
    ) as ids:
        response = await send_request(
            HTTPMethod.DELETE,
            f"tournaments/{ids['tournament']}",
            headers=auth_context.headers,
        )
        assert response == {"detail": "赛事已结算；请先撤销结算再删除或修改"}


@pytest.mark.asyncio(loop_scope="session")
async def test_create_team_on_rated_individual_blocked(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """POST teams (free-text) on a rated individual tournament -> 400 (util.py 163)."""
    async with rated_individual_tournament(auth_context.club.id, endpoint="no_freetext") as ids:
        response = await send_request(
            HTTPMethod.POST,
            f"tournaments/{ids['tournament']}/teams",
            json={"name": "Free Text Team", "active": True, "player_names": []},
            headers=auth_context.headers,
        )
        assert response["detail"].startswith("个人积分赛只能通过选择已注册账号来添加参赛者")


# --------------------------------------------------------------------------- #
# auth.py 118-126 (admin 403) and 142 (record-results 401)
# --------------------------------------------------------------------------- #


def _non_member_user(suffix: str) -> UserInsertable:
    return UserInsertable(
        email=f"gapsapi_{suffix}-{datetime_utc.now().timestamp()}@example.org",
        name="Outsider",
        password_hash="x",
        created=datetime_utc.now(),
        account_type=UserAccountType.REGULAR,
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_non_admin_create_rating_category_403(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """A logged-in NON-admin posting to an admin-only endpoint -> 403
    (auth.py user_authenticated_admin, 118-126). The auth_context owner is not
    a site admin."""
    response = await send_request(
        HTTPMethod.POST,
        "rating-categories",
        json={"key": "GAPSAPI_NOADMIN", "name": "X", "algorithm": "chinatt"},
        headers=auth_context.headers,
    )
    assert response == {"detail": "该操作需要站点管理员权限"}


@pytest.mark.asyncio(loop_scope="session")
async def test_admin_create_rating_category_success(
    startup_and_shutdown_uvicorn_server: None,
) -> None:
    """A site admin posting to the admin-only endpoint succeeds, exercising the
    success return of user_authenticated_admin (auth.py line 126)."""
    admin = UserInsertable(
        email=f"gapsapi_admin-{datetime_utc.now().timestamp()}@example.org",
        name="Site Admin",
        password_hash="x",
        created=datetime_utc.now(),
        account_type=UserAccountType.REGULAR,
        is_admin=True,
    )
    async with inserted_user(admin) as admin_user:
        headers = {"Authorization": f"Bearer {get_mock_token(admin_user.email)}"}
        key = f"GAPSAPI_OK_{datetime_utc.now().timestamp()}".replace(".", "_")
        try:
            response = await send_request(
                HTTPMethod.POST,
                "rating-categories",
                json={"key": key, "name": "Created By Admin", "algorithm": "chinatt"},
                headers=headers,
            )
            assert response.get("data", {}).get("key") == key
        finally:
            await database.execute("DELETE FROM rating_categories WHERE key = :k", {"k": key})


@pytest.mark.asyncio(loop_scope="session")
async def test_record_results_without_access_401(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """A logged-in user who is neither a club member nor a scorer tries to update
    a match score -> 401 (auth.py user_can_record_results, line 142)."""
    async with (
        inserted_user(_non_member_user("norights")) as outsider,
        rated_individual_tournament(
            auth_context.club.id, endpoint="norights", with_match=True
        ) as ids,
    ):
        headers = {"Authorization": f"Bearer {get_mock_token(outsider.email)}"}
        body = {
            "stage_item_input1_score": 11,
            "stage_item_input2_score": 9,
            "round_id": ids["round"],
            "court_id": None,
        }
        response = await send_request(
            HTTPMethod.PUT,
            f"tournaments/{ids['tournament']}/matches/{ids['match']}",
            json=body,
            headers=headers,
        )
        assert response == {"detail": "你没有权限为本比赛录入比分"}
