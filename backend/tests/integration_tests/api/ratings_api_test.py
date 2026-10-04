"""HTTP API tests for bracket/routes/ratings.py (and the SQL it drives).

A `rated_tournament` fixture builds a rated individual tournament parented to the
session `auth_context.club`, so `auth_context.headers` (a club owner) authorizes
the owner-scoped endpoints. A separate ADMIN user/token authorizes the admin and
category endpoints. Every row is cleaned up FK-safely with a unique "ratapi_"
prefix so this file never collides with other suites.
"""

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from heliclockter import datetime_utc

from bracket.database import database
from bracket.models.db.rating import SettlementResult, SettlementStatus
from bracket.sql.ratings import count_unrated_participants
from bracket.utils.http import HTTPMethod
from tests.integration_tests.api.shared import send_request
from tests.integration_tests.mocks import get_mock_token
from tests.integration_tests.models import AuthContext


async def _insert(query: str, values: dict) -> int:
    return await database.fetch_val(query + " RETURNING id", values)


def _uniq(prefix: str) -> str:
    return f"ratapi_{prefix}_{uuid4()}"


@pytest_asyncio.fixture(loop_scope="session")
async def admin_headers() -> AsyncIterator[dict[str, str]]:
    email = _uniq("admin") + "@test"
    admin_id = await _insert(
        "INSERT INTO users (email, name, password_hash, account_type, is_admin) "
        "VALUES (:e, 'RatApiAdmin', 'x', 'REGULAR', true)",
        {"e": email},
    )
    try:
        yield {"Authorization": f"Bearer {get_mock_token(email)}"}
    finally:
        await database.execute("DELETE FROM users WHERE id = :i", {"i": admin_id})


@pytest_asyncio.fixture(loop_scope="session")
async def rated_tournament(auth_context: AuthContext) -> AsyncIterator[dict]:
    """A rated individual tournament parented to auth_context.club, with two bound
    accounts (ACTIVE ratings), bound teams, and a non-draft round with a decided
    match. Mirrors rating_settlement_test.py but reuses the owner's club."""
    now = datetime_utc.now()
    ids: dict = {}
    try:
        ids["category"] = await _insert(
            "INSERT INTO rating_categories (key, name, algorithm) VALUES (:k, :n, 'chinatt')",
            {"k": _uniq("cat"), "n": "RatApi Category"},
        )
        ids["tournament"] = await _insert(
            """
            INSERT INTO tournaments
                (name, start_time, club_id, dashboard_public, is_individual, rating_category_id)
            VALUES ('RatApi T', :now, :club, true, true, :cat)
            """,
            {"now": now, "club": auth_context.club.id, "cat": ids["category"]},
        )
        ids["userA"] = await _insert(
            "INSERT INTO users (email, name, password_hash, account_type) "
            "VALUES (:e, 'RatApi Alice', 'x', 'REGULAR')",
            {"e": _uniq("alice") + "@test"},
        )
        ids["userB"] = await _insert(
            "INSERT INTO users (email, name, password_hash, account_type) "
            "VALUES (:e, 'RatApi Bob', 'x', 'REGULAR')",
            {"e": _uniq("bob") + "@test"},
        )
        for who, rating in (("A", 1500), ("B", 1450)):
            await database.execute(
                "INSERT INTO player_ratings "
                "(category_id, user_id, initial_rating, current_rating, status, last_updated) "
                "VALUES (:c, :u, :r, :r, 'ACTIVE', :now)",
                {"c": ids["category"], "u": ids[f"user{who}"], "r": rating, "now": now},
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
        ids["round"] = await _insert(
            "INSERT INTO rounds (name, is_draft, stage_item_id) VALUES ('R', false, :si)",
            {"si": ids["stage_item"]},
        )
        for who in ("A", "B"):
            ids[f"team{who}"] = await _insert(
                "INSERT INTO teams (name, tournament_id) VALUES (:n, :t)",
                {"n": who, "t": ids["tournament"]},
            )
            await database.execute(
                "INSERT INTO teams_x_users (team_id, user_id, tournament_id) VALUES (:tm, :u, :t)",
                {"tm": ids[f"team{who}"], "u": ids[f"user{who}"], "t": ids["tournament"]},
            )
            ids[f"input{who}"] = await _insert(
                "INSERT INTO stage_item_inputs (slot, tournament_id, stage_item_id, team_id) "
                "VALUES (:slot, :t, :si, :tm)",
                {
                    "slot": 0 if who == "A" else 1,
                    "t": ids["tournament"],
                    "si": ids["stage_item"],
                    "tm": ids[f"team{who}"],
                },
            )
        ids["match"] = await _insert(
            """
            INSERT INTO matches
                (round_id, stage_item_input1_id, stage_item_input2_id,
                 stage_item_input1_conflict, stage_item_input2_conflict,
                 stage_item_input1_score, stage_item_input2_score)
            VALUES (:r, :i1, :i2, false, false, 3, 1)
            """,
            {"r": ids["round"], "i1": ids["inputA"], "i2": ids["inputB"]},
        )
        yield ids
    finally:
        for table, col, key in [
            ("rating_events", "tournament_id", "tournament"),
            ("matches", "round_id", "round"),
            ("stage_item_inputs", "stage_item_id", "stage_item"),
            ("rounds", "id", "round"),
            ("stage_items", "id", "stage_item"),
            ("stages", "id", "stage"),
            ("teams_x_users", "tournament_id", "tournament"),
            ("teams", "tournament_id", "tournament"),
            ("rankings", "tournament_id", "tournament"),
            ("player_ratings", "category_id", "category"),
            ("tournaments", "id", "tournament"),
            ("users", "id", "userA"),
            ("users", "id", "userB"),
            ("rating_categories", "id", "category"),
        ]:
            if key in ids:
                await database.execute(f"DELETE FROM {table} WHERE {col} = :v", {"v": ids[key]})


# --- Rating categories ---


@pytest.mark.asyncio(loop_scope="session")
async def test_list_rating_categories(auth_context: AuthContext, rated_tournament: dict) -> None:
    resp = await send_request(HTTPMethod.GET, "rating-categories", headers=auth_context.headers)
    cat_ids = [c["id"] for c in resp["data"]]
    assert rated_tournament["category"] in cat_ids


@pytest.mark.asyncio(loop_scope="session")
async def test_create_category_and_unique_violation(admin_headers: dict[str, str]) -> None:
    key = _uniq("createcat")
    created = await send_request(
        HTTPMethod.POST,
        "rating-categories",
        json={"key": key, "name": "Created", "algorithm": "chinatt"},
        headers=admin_headers,
    )
    new_id = created["data"]["id"]
    assert created["data"]["key"] == key
    try:
        # Same key again -> unique-constraint path -> 400.
        dup = await send_request(
            HTTPMethod.POST,
            "rating-categories",
            json={"key": key, "name": "Dup", "algorithm": "chinatt"},
            headers=admin_headers,
        )
        assert "已存在" in dup["detail"]
    finally:
        await database.execute("DELETE FROM rating_categories WHERE id = :i", {"i": new_id})


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_builtin_category_blocked(admin_headers: dict[str, str]) -> None:
    """The seeded 加华积分 category (key=CanadaChinaTT) must survive any delete attempt."""
    row = await database.fetch_one("SELECT id FROM rating_categories WHERE key = 'CanadaChinaTT'")
    inserted = row is None
    if inserted:
        cat_id = await database.fetch_val(
            "INSERT INTO rating_categories (key, name, algorithm) "
            "VALUES ('CanadaChinaTT', '加华积分', 'chinatt') RETURNING id"
        )
    else:
        cat_id = row["id"]
    try:
        resp = await send_request(
            HTTPMethod.DELETE, f"rating-categories/{cat_id}", headers=admin_headers
        )
        assert "不可删除" in resp["detail"]
        still = await database.fetch_one(
            "SELECT id FROM rating_categories WHERE id = :i", {"i": cat_id}
        )
        assert still is not None
    finally:
        if inserted:
            await database.execute("DELETE FROM rating_categories WHERE id = :i", {"i": cat_id})


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_category_in_use_blocked(
    admin_headers: dict[str, str], rated_tournament: dict
) -> None:
    """A category referenced by tournaments/ratings is rejected cleanly, not with a 500."""
    resp = await send_request(
        HTTPMethod.DELETE,
        f"rating-categories/{rated_tournament['category']}",
        headers=admin_headers,
    )
    assert "仍被比赛或选手积分引用" in resp["detail"]


@pytest.mark.asyncio(loop_scope="session")
async def test_create_category_requires_admin(auth_context: AuthContext) -> None:
    resp = await send_request(
        HTTPMethod.POST,
        "rating-categories",
        json={"key": _uniq("nope"), "name": "X", "algorithm": "chinatt"},
        headers=auth_context.headers,
    )
    assert "管理员" in resp["detail"]


@pytest.mark.asyncio(loop_scope="session")
async def test_update_category_success_and_404(
    admin_headers: dict[str, str], rated_tournament: dict
) -> None:
    cat_id = rated_tournament["category"]
    updated = await send_request(
        HTTPMethod.PUT,
        f"rating-categories/{cat_id}",
        json={"name": "Renamed", "algorithm": "chinatt"},
        headers=admin_headers,
    )
    assert updated["data"]["name"] == "Renamed"

    missing = await send_request(
        HTTPMethod.PUT,
        "rating-categories/999999999",
        json={"name": "X", "algorithm": "chinatt"},
        headers=admin_headers,
    )
    assert "找不到" in missing["detail"].lower()


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_category_success(admin_headers: dict[str, str]) -> None:
    new_id = await _insert(
        "INSERT INTO rating_categories (key, name, algorithm) VALUES (:k, 'Del', 'chinatt')",
        {"k": _uniq("delcat")},
    )
    resp = await send_request(
        HTTPMethod.DELETE, f"rating-categories/{new_id}", headers=admin_headers
    )
    assert resp.get("success") is True
    remaining = await database.fetch_val(
        "SELECT COUNT(*) FROM rating_categories WHERE id = :i", {"i": new_id}
    )
    assert remaining == 0


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_category_blocked_by_settled_tournament(
    admin_headers: dict[str, str], rated_tournament: dict
) -> None:
    cat_id = rated_tournament["category"]
    # Mark the tournament settled against this category, blocking deletion.
    await database.execute(
        "UPDATE tournaments SET settled_seq = 1 WHERE id = :t",
        {"t": rated_tournament["tournament"]},
    )
    try:
        resp = await send_request(
            HTTPMethod.DELETE, f"rating-categories/{cat_id}", headers=admin_headers
        )
        assert "已有结算赛事" in resp["detail"]
    finally:
        await database.execute(
            "UPDATE tournaments SET settled_seq = NULL WHERE id = :t",
            {"t": rated_tournament["tournament"]},
        )


@pytest.mark.asyncio(loop_scope="session")
async def test_leaderboard(rated_tournament: dict) -> None:
    cat_id = rated_tournament["category"]
    # Public endpoint (no auth). Both seeded players are ACTIVE -> shown.
    resp = await send_request(HTTPMethod.GET, f"rating-categories/{cat_id}/leaderboard")
    user_ids = {e["user_id"] for e in resp["data"]}
    assert rated_tournament["userA"] in user_ids
    assert rated_tournament["userB"] in user_ids
    ratings = {e["user_id"]: e["current_rating"] for e in resp["data"]}
    assert ratings[rated_tournament["userA"]] == 1500


# --- Admin review queue + approve-and-settle ---


@pytest.mark.asyncio(loop_scope="session")
async def test_settlement_reviews_and_approve_and_settle(
    admin_headers: dict[str, str], rated_tournament: dict
) -> None:
    ids = rated_tournament
    # Flip seeds to PENDING and request settlement so it appears in the queue.
    await database.execute(
        "UPDATE player_ratings SET status = 'PENDING' WHERE category_id = :c",
        {"c": ids["category"]},
    )
    await database.execute(
        "UPDATE tournaments SET settlement_requested_at = :now WHERE id = :t",
        {"now": datetime_utc.now(), "t": ids["tournament"]},
    )

    reviews = await send_request(HTTPMethod.GET, "admin/settlement-reviews", headers=admin_headers)
    mine = [r for r in reviews["data"] if r["tournament_id"] == ids["tournament"]]
    assert len(mine) == 1
    assert len(mine[0]["players"]) == 2

    alice_pr = await database.fetch_val(
        "SELECT id FROM player_ratings WHERE category_id = :c AND user_id = :u",
        {"c": ids["category"], "u": ids["userA"]},
    )
    settled = await send_request(
        HTTPMethod.POST,
        f"admin/settlements/{ids['tournament']}/approve-and-settle",
        json={"adjustments": [{"player_rating_id": alice_pr, "initial_rating": 1600}]},
        headers=admin_headers,
    )
    assert settled["data"]["status"] == "SETTLED"

    rows = {
        r["user_id"]: r
        for r in await database.fetch_all(
            "SELECT user_id, initial_rating, status FROM player_ratings WHERE category_id = :c",
            {"c": ids["category"]},
        )
    }
    assert rows[ids["userA"]]["initial_rating"] == 1600
    assert rows[ids["userA"]]["status"] == "ACTIVE"
    assert rows[ids["userB"]]["status"] == "ACTIVE"
    # settlement_requested_at cleared by approve-and-settle.
    req = await database.fetch_val(
        "SELECT settlement_requested_at FROM tournaments WHERE id = :t",
        {"t": ids["tournament"]},
    )
    assert req is None


@pytest.mark.asyncio(loop_scope="session")
async def test_approve_and_settle_settle_did_not_complete(
    admin_headers: dict[str, str], rated_tournament: dict
) -> None:
    """Defensive rollback: if settle_tournament returns a non-SETTLED result after
    the seeds were just approved, the route raises SettlementError -> 400."""
    ids = rated_tournament
    await database.execute(
        "UPDATE player_ratings SET status = 'PENDING' WHERE category_id = :c",
        {"c": ids["category"]},
    )
    not_settled = SettlementResult(
        status=SettlementStatus.PENDING_REVIEW,
        pending_review_count=1,
        message="still pending somehow",
    )
    with patch(
        "bracket.routes.ratings.settle_tournament",
        AsyncMock(return_value=not_settled),
    ):
        resp = await send_request(
            HTTPMethod.POST,
            f"admin/settlements/{ids['tournament']}/approve-and-settle",
            json={"adjustments": []},
            headers=admin_headers,
        )
    assert "still pending somehow" in resp["detail"]
    # Rolled back: seeds stayed PENDING despite the approve loop running.
    statuses = await database.fetch_all(
        "SELECT status FROM player_ratings WHERE category_id = :c", {"c": ids["category"]}
    )
    assert all(r["status"] == "PENDING" for r in statuses)


@pytest.mark.asyncio(loop_scope="session")
async def test_count_unrated_participants(rated_tournament: dict) -> None:
    ids = rated_tournament
    # Both participants have a rating row -> none unrated.
    assert await count_unrated_participants(ids["tournament"], ids["category"]) == 0
    # Drop userB's rating -> one unrated participant.
    await database.execute(
        "DELETE FROM player_ratings WHERE category_id = :c AND user_id = :u",
        {"c": ids["category"], "u": ids["userB"]},
    )
    assert await count_unrated_participants(ids["tournament"], ids["category"]) == 1


@pytest.mark.asyncio(loop_scope="session")
async def test_approve_and_settle_non_rated(
    admin_headers: dict[str, str], auth_context: AuthContext
) -> None:
    # auth_context.tournament is not individual/rated -> _require_rated_individual 400.
    resp = await send_request(
        HTTPMethod.POST,
        f"admin/settlements/{auth_context.tournament.id}/approve-and-settle",
        json={"adjustments": []},
        headers=admin_headers,
    )
    assert "不参与积分" in resp["detail"]


@pytest.mark.asyncio(loop_scope="session")
async def test_approve_and_settle_settlement_error(
    admin_headers: dict[str, str], rated_tournament: dict
) -> None:
    ids = rated_tournament
    # Zero out the match -> "no recorded result" SettlementError -> 400.
    await database.execute(
        "UPDATE matches SET stage_item_input1_score = 0, stage_item_input2_score = 0 WHERE id = :m",
        {"m": ids["match"]},
    )
    resp = await send_request(
        HTTPMethod.POST,
        f"admin/settlements/{ids['tournament']}/approve-and-settle",
        json={"adjustments": []},
        headers=admin_headers,
    )
    assert "没有录入结果" in resp["detail"]


# --- Owner: seed-rating ---


@pytest.mark.asyncio(loop_scope="session")
async def test_seed_rating_happy(auth_context: AuthContext, rated_tournament: dict) -> None:
    ids = rated_tournament
    # Make userB's rating PENDING so seeding is allowed (ACTIVE would be blocked).
    await database.execute(
        "UPDATE player_ratings SET status = 'PENDING' WHERE category_id = :c AND user_id = :u",
        {"c": ids["category"], "u": ids["userB"]},
    )
    resp = await send_request(
        HTTPMethod.PUT,
        f"tournaments/{ids['tournament']}/teams/{ids['teamB']}/seed-rating",
        json={"rating": 1700},
        headers=auth_context.headers,
    )
    assert resp["data"]["initial_rating"] == 1700
    assert resp["data"]["status"] == "PENDING"


@pytest.mark.asyncio(loop_scope="session")
async def test_seed_rating_active_blocked(
    auth_context: AuthContext, rated_tournament: dict
) -> None:
    ids = rated_tournament
    # userA stays ACTIVE -> blocked.
    resp = await send_request(
        HTTPMethod.PUT,
        f"tournaments/{ids['tournament']}/teams/{ids['teamA']}/seed-rating",
        json={"rating": 1700},
        headers=auth_context.headers,
    )
    assert "已有生效积分" in resp["detail"]


@pytest.mark.asyncio(loop_scope="session")
async def test_seed_rating_settled_blocked(
    auth_context: AuthContext, rated_tournament: dict
) -> None:
    ids = rated_tournament
    await database.execute(
        "UPDATE tournaments SET settled_seq = 1 WHERE id = :t", {"t": ids["tournament"]}
    )
    try:
        resp = await send_request(
            HTTPMethod.PUT,
            f"tournaments/{ids['tournament']}/teams/{ids['teamA']}/seed-rating",
            json={"rating": 1700},
            headers=auth_context.headers,
        )
        assert "已结算的赛事不能再修改初始积分" in resp["detail"]
    finally:
        await database.execute(
            "UPDATE tournaments SET settled_seq = NULL WHERE id = :t",
            {"t": ids["tournament"]},
        )


@pytest.mark.asyncio(loop_scope="session")
async def test_seed_rating_unbound_team(auth_context: AuthContext, rated_tournament: dict) -> None:
    ids = rated_tournament
    # Create a team in this tournament with no bound account.
    unbound_team = await _insert(
        "INSERT INTO teams (name, tournament_id) VALUES ('Unbound', :t)",
        {"t": ids["tournament"]},
    )
    try:
        resp = await send_request(
            HTTPMethod.PUT,
            f"tournaments/{ids['tournament']}/teams/{unbound_team}/seed-rating",
            json={"rating": 1700},
            headers=auth_context.headers,
        )
        assert "尚未绑定账号" in resp["detail"]
    finally:
        await database.execute("DELETE FROM teams WHERE id = :i", {"i": unbound_team})


@pytest.mark.asyncio(loop_scope="session")
async def test_seed_rating_non_rated(auth_context: AuthContext) -> None:
    # auth_context's own (non-rated) tournament: need a team in it.
    team_id = await _insert(
        "INSERT INTO teams (name, tournament_id) VALUES ('NR', :t)",
        {"t": auth_context.tournament.id},
    )
    try:
        resp = await send_request(
            HTTPMethod.PUT,
            f"tournaments/{auth_context.tournament.id}/teams/{team_id}/seed-rating",
            json={"rating": 1700},
            headers=auth_context.headers,
        )
        assert "不参与积分" in resp["detail"]
    finally:
        await database.execute("DELETE FROM teams WHERE id = :i", {"i": team_id})


# --- Owner: settlement-request ---


@pytest.mark.asyncio(loop_scope="session")
async def test_settlement_request_direct_settle(
    auth_context: AuthContext, rated_tournament: dict
) -> None:
    ids = rated_tournament
    # All seeds ACTIVE -> direct settle.
    resp = await send_request(
        HTTPMethod.POST,
        f"tournaments/{ids['tournament']}/settlement-request",
        headers=auth_context.headers,
    )
    assert resp["data"]["status"] == "SETTLED"


@pytest.mark.asyncio(loop_scope="session")
async def test_settlement_request_pending_review(
    auth_context: AuthContext, rated_tournament: dict
) -> None:
    ids = rated_tournament
    await database.execute(
        "UPDATE player_ratings SET status = 'PENDING' WHERE category_id = :c",
        {"c": ids["category"]},
    )
    resp = await send_request(
        HTTPMethod.POST,
        f"tournaments/{ids['tournament']}/settlement-request",
        headers=auth_context.headers,
    )
    assert resp["data"]["status"] == "PENDING_REVIEW"
    assert resp["data"]["settlement_requested"] is True
    assert "待管理员审核" in resp["data"]["message"]
    req = await database.fetch_val(
        "SELECT settlement_requested_at FROM tournaments WHERE id = :t",
        {"t": ids["tournament"]},
    )
    assert req is not None


@pytest.mark.asyncio(loop_scope="session")
async def test_settlement_request_error(auth_context: AuthContext, rated_tournament: dict) -> None:
    ids = rated_tournament
    await database.execute(
        "UPDATE matches SET stage_item_input1_score = 0, stage_item_input2_score = 0 WHERE id = :m",
        {"m": ids["match"]},
    )
    resp = await send_request(
        HTTPMethod.POST,
        f"tournaments/{ids['tournament']}/settlement-request",
        headers=auth_context.headers,
    )
    assert "没有录入结果" in resp["detail"]


# --- Admin: settle ---


@pytest.mark.asyncio(loop_scope="session")
async def test_settle_happy(admin_headers: dict[str, str], rated_tournament: dict) -> None:
    ids = rated_tournament
    resp = await send_request(
        HTTPMethod.POST,
        f"tournaments/{ids['tournament']}/settle",
        headers=admin_headers,
    )
    assert resp["data"]["status"] == "SETTLED"
    assert resp["data"]["settled_seq"] is not None


@pytest.mark.asyncio(loop_scope="session")
async def test_settle_pending_review_blocked(
    admin_headers: dict[str, str], rated_tournament: dict
) -> None:
    ids = rated_tournament
    await database.execute(
        "UPDATE player_ratings SET status = 'PENDING' WHERE category_id = :c",
        {"c": ids["category"]},
    )
    resp = await send_request(
        HTTPMethod.POST,
        f"tournaments/{ids['tournament']}/settle",
        headers=admin_headers,
    )
    assert "仍在审核中" in resp["detail"]


@pytest.mark.asyncio(loop_scope="session")
async def test_settle_settlement_error(
    admin_headers: dict[str, str], rated_tournament: dict
) -> None:
    ids = rated_tournament
    await database.execute(
        "UPDATE matches SET stage_item_input1_score = 0, stage_item_input2_score = 0 WHERE id = :m",
        {"m": ids["match"]},
    )
    resp = await send_request(
        HTTPMethod.POST,
        f"tournaments/{ids['tournament']}/settle",
        headers=admin_headers,
    )
    assert "没有录入结果" in resp["detail"]


# --- Owner: settlement-status ---


@pytest.mark.asyncio(loop_scope="session")
async def test_settlement_status_already_settled(
    auth_context: AuthContext, rated_tournament: dict
) -> None:
    ids = rated_tournament
    await database.execute(
        "UPDATE tournaments SET settled_seq = 7 WHERE id = :t", {"t": ids["tournament"]}
    )
    try:
        resp = await send_request(
            HTTPMethod.GET,
            f"tournaments/{ids['tournament']}/settlement-status",
            headers=auth_context.headers,
        )
        assert resp["data"]["status"] == "SETTLED"
        assert resp["data"]["settled_seq"] == 7
        assert resp["data"]["message"] == "Settled"
    finally:
        await database.execute(
            "UPDATE tournaments SET settled_seq = NULL WHERE id = :t",
            {"t": ids["tournament"]},
        )


@pytest.mark.asyncio(loop_scope="session")
async def test_settlement_status_ready(auth_context: AuthContext, rated_tournament: dict) -> None:
    ids = rated_tournament
    # All ACTIVE -> pending == 0 -> "可以结算".
    resp = await send_request(
        HTTPMethod.GET,
        f"tournaments/{ids['tournament']}/settlement-status",
        headers=auth_context.headers,
    )
    assert resp["data"]["pending_review_count"] == 0
    assert resp["data"]["message"] == "可以结算"


@pytest.mark.asyncio(loop_scope="session")
async def test_settlement_status_requested(
    auth_context: AuthContext, rated_tournament: dict
) -> None:
    ids = rated_tournament
    await database.execute(
        "UPDATE player_ratings SET status = 'PENDING' WHERE category_id = :c",
        {"c": ids["category"]},
    )
    await database.execute(
        "UPDATE tournaments SET settlement_requested_at = :now WHERE id = :t",
        {"now": datetime_utc.now(), "t": ids["tournament"]},
    )
    resp = await send_request(
        HTTPMethod.GET,
        f"tournaments/{ids['tournament']}/settlement-status",
        headers=auth_context.headers,
    )
    assert resp["data"]["status"] == "PENDING_REVIEW"
    assert resp["data"]["settlement_requested"] is True
    assert "待管理员审核" in resp["data"]["message"]


@pytest.mark.asyncio(loop_scope="session")
async def test_settlement_status_pending_not_requested(
    auth_context: AuthContext, rated_tournament: dict
) -> None:
    ids = rated_tournament
    await database.execute(
        "UPDATE player_ratings SET status = 'PENDING' WHERE category_id = :c",
        {"c": ids["category"]},
    )
    resp = await send_request(
        HTTPMethod.GET,
        f"tournaments/{ids['tournament']}/settlement-status",
        headers=auth_context.headers,
    )
    assert resp["data"]["pending_review_count"] == 2
    assert "有 2 名选手" in resp["data"]["message"]


@pytest.mark.asyncio(loop_scope="session")
async def test_settlement_status_error(auth_context: AuthContext, rated_tournament: dict) -> None:
    ids = rated_tournament
    await database.execute(
        "UPDATE matches SET stage_item_input1_score = 0, stage_item_input2_score = 0 WHERE id = :m",
        {"m": ids["match"]},
    )
    resp = await send_request(
        HTTPMethod.GET,
        f"tournaments/{ids['tournament']}/settlement-status",
        headers=auth_context.headers,
    )
    assert "没有录入结果" in resp["detail"]


# --- My ratings (current user) ---


async def _headers_for_user(user_id: int) -> dict[str, str]:
    email = await database.fetch_val("SELECT email FROM users WHERE id = :i", {"i": user_id})
    return {"Authorization": f"Bearer {get_mock_token(email)}"}


@pytest.mark.asyncio(loop_scope="session")
async def test_my_ratings_and_events_after_settlement(
    admin_headers: dict[str, str], rated_tournament: dict
) -> None:
    ids = rated_tournament
    settled = await send_request(
        HTTPMethod.POST, f"tournaments/{ids['tournament']}/settle", headers=admin_headers
    )
    assert settled["data"]["status"] == "SETTLED"

    alice_headers = await _headers_for_user(ids["userA"])
    ratings = await send_request(HTTPMethod.GET, "me/ratings", headers=alice_headers)
    mine = [r for r in ratings["data"] if r["category_id"] == ids["category"]]
    assert len(mine) == 1
    summary = mine[0]
    assert summary["status"] == "ACTIVE"
    assert summary["matches_played"] == 1
    # Alice (seeded 1500) won 3-1 against Bob (seeded 1450) -> rating went up.
    assert summary["current_rating"] > 1500
    assert summary["yearly_avg_rating"] == pytest.approx(summary["current_rating"])
    assert summary["peak_rating"] == summary["current_rating"]

    events = await send_request(
        HTTPMethod.GET, f"me/ratings/{ids['category']}/events", headers=alice_headers
    )
    assert len(events["data"]) == 1
    event = events["data"][0]
    assert event["result"] == "W"
    assert event["opponent_name"] == "RatApi Bob"
    assert event["tournament_name"] == "RatApi T"
    assert event["rating_before"] == 1500
    assert event["rating_after"] == summary["current_rating"]


@pytest.mark.asyncio(loop_scope="session")
async def test_my_ratings_empty_for_user_without_ratings(auth_context: AuthContext) -> None:
    resp = await send_request(HTTPMethod.GET, "me/ratings", headers=auth_context.headers)
    assert resp["data"] == []


@pytest.mark.asyncio(loop_scope="session")
async def test_my_ratings_cumulative_across_multiple_matches_in_one_tournament(
    admin_headers: dict[str, str], auth_context: AuthContext
) -> None:
    """A player with two matches in the same settled tournament must have their
    rating update sequentially: match 2 is scored off the rating AFTER match 1,
    not the pre-tournament rating (matches settlement.py's sequential design,
    mirroring 开球网/ChinaTT). /me/ratings and /me/ratings/{c}/events must reflect
    that real, per-match progression.
    """
    now = datetime_utc.now()
    ids: dict = {}
    try:
        ids["category"] = await _insert(
            "INSERT INTO rating_categories (key, name, algorithm) VALUES (:k, :n, 'chinatt')",
            {"k": _uniq("cumcat"), "n": "Cum Category"},
        )
        ids["tournament"] = await _insert(
            """
            INSERT INTO tournaments
                (name, start_time, club_id, dashboard_public, is_individual, rating_category_id)
            VALUES ('Cum T', :now, :club, true, true, :cat)
            """,
            {"now": now, "club": auth_context.club.id, "cat": ids["category"]},
        )
        for who in ("A", "B", "C"):
            ids[f"user{who}"] = await _insert(
                "INSERT INTO users (email, name, password_hash, account_type) "
                "VALUES (:e, :n, 'x', 'REGULAR')",
                {"e": _uniq(who.lower()) + "@test", "n": f"Cum {who}"},
            )
        for who, rating in (("A", 1500), ("B", 1450), ("C", 1450)):
            await database.execute(
                "INSERT INTO player_ratings "
                "(category_id, user_id, initial_rating, current_rating, status, last_updated) "
                "VALUES (:c, :u, :r, :r, 'ACTIVE', :now)",
                {"c": ids["category"], "u": ids[f"user{who}"], "r": rating, "now": now},
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
            "VALUES ('SI', :s, 3, :r, 'ROUND_ROBIN')",
            {"s": ids["stage"], "r": ids["ranking"]},
        )
        ids["round"] = await _insert(
            "INSERT INTO rounds (name, is_draft, stage_item_id) VALUES ('R', false, :si)",
            {"si": ids["stage_item"]},
        )
        inputs: dict[str, int] = {}
        for slot, who in enumerate(("A", "B", "C")):
            team = await _insert(
                "INSERT INTO teams (name, tournament_id) VALUES (:n, :t)",
                {"n": who, "t": ids["tournament"]},
            )
            await database.execute(
                "INSERT INTO teams_x_users (team_id, user_id, tournament_id) VALUES (:tm, :u, :t)",
                {"tm": team, "u": ids[f"user{who}"], "t": ids["tournament"]},
            )
            inputs[who] = await _insert(
                "INSERT INTO stage_item_inputs (slot, tournament_id, stage_item_id, team_id) "
                "VALUES (:slot, :t, :si, :tm)",
                {"slot": slot, "t": ids["tournament"], "si": ids["stage_item"], "tm": team},
            )
        # Alice beats both Bob and Carol -> two wins settled in the SAME batch.
        for opp in ("B", "C"):
            await _insert(
                """
                INSERT INTO matches
                    (round_id, stage_item_input1_id, stage_item_input2_id,
                     stage_item_input1_conflict, stage_item_input2_conflict,
                     stage_item_input1_score, stage_item_input2_score)
                VALUES (:r, :i1, :i2, false, false, 3, 1)
                """,
                {"r": ids["round"], "i1": inputs["A"], "i2": inputs[opp]},
            )

        settled = await send_request(
            HTTPMethod.POST, f"tournaments/{ids['tournament']}/settle", headers=admin_headers
        )
        assert settled["data"]["status"] == "SETTLED"

        alice_headers = await _headers_for_user(ids["userA"])
        ratings = await send_request(HTTPMethod.GET, "me/ratings", headers=alice_headers)
        summary = next(r for r in ratings["data"] if r["category_id"] == ids["category"])
        assert summary["matches_played"] == 2
        # 1500 vs 1450 (diff 50, +6) then 1506 vs 1450 (diff 56, still +6) = 1512.
        assert summary["current_rating"] == 1512
        assert summary["peak_rating"] == summary["current_rating"]

        events = await send_request(
            HTTPMethod.GET, f"me/ratings/{ids['category']}/events", headers=alice_headers
        )
        alice_events = [e for e in events["data"] if e["user_id"] == ids["userA"]]
        assert len(alice_events) == 2
        # Match 1 (vs Bob, scheduled first) is scored off the pre-tournament rating.
        assert alice_events[0]["rating_before"] == 1500
        assert alice_events[0]["rating_after"] == 1506
        # Match 2 (vs Carol, scheduled second) is scored off the UPDATED rating
        # from match 1, not the frozen pre-tournament one.
        assert alice_events[1]["rating_before"] == 1506
        assert alice_events[1]["rating_after"] == 1512
        assert alice_events[1]["rating_after"] == summary["current_rating"]
    finally:
        for table, col, key in [
            ("rating_events", "tournament_id", "tournament"),
            ("matches", "round_id", "round"),
            ("stage_item_inputs", "stage_item_id", "stage_item"),
            ("rounds", "id", "round"),
            ("stage_items", "id", "stage_item"),
            ("stages", "id", "stage"),
            ("teams_x_users", "tournament_id", "tournament"),
            ("teams", "tournament_id", "tournament"),
            ("rankings", "tournament_id", "tournament"),
            ("player_ratings", "category_id", "category"),
            ("tournaments", "id", "tournament"),
            ("users", "id", "userA"),
            ("users", "id", "userB"),
            ("users", "id", "userC"),
            ("rating_categories", "id", "category"),
        ]:
            if key in ids:
                await database.execute(f"DELETE FROM {table} WHERE {col} = :v", {"v": ids[key]})
