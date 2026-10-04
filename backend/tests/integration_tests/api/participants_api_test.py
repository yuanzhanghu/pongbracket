"""API tests for the participants routes (join/leave, trusted managers, scorers,
addable participants, direct add).

Builds individual tournaments parented to ``auth_context.club`` so the session
owner is authorised for the ``user_authenticated_for_tournament`` endpoints, and
creates extra accounts (with their own bearer tokens) to exercise the
second-user join/leave and trust flows. Every row is torn down FK-safely with a
unique email per account to avoid collisions with other test files.
"""

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from heliclockter import datetime_utc

from bracket.database import database
from bracket.logic.participants import admit_user_to_tournament
from bracket.sql.tournaments import sql_get_tournament
from bracket.utils.http import HTTPMethod
from bracket.utils.id_types import UserId
from tests.integration_tests.api.shared import (
    SUCCESS_RESPONSE,
    send_auth_request,
    send_request,
)
from tests.integration_tests.mocks import generate_email, get_mock_token
from tests.integration_tests.models import AuthContext


async def _insert(query: str, values: dict) -> int:
    return await database.fetch_val(query + " RETURNING id", values)


async def _make_user(name: str) -> tuple[int, str, dict[str, str]]:
    """Insert a REGULAR account with a unique email; return (id, email, headers)."""
    email = f"partapi_{generate_email()}"
    user_id = await _insert(
        "INSERT INTO users (email, name, password_hash, account_type) "
        "VALUES (:e, :n, 'x', 'REGULAR')",
        {"e": email, "n": name},
    )
    headers = {"Authorization": f"Bearer {get_mock_token(email)}"}
    return user_id, email, headers


async def _make_tournament(club_id: int, *, is_individual: bool = True) -> int:
    now = datetime_utc.now()
    return await _insert(
        """
        INSERT INTO tournaments
            (name, start_time, club_id, dashboard_public, is_individual)
        VALUES ('PartAPI', :now, :club, true, :ind)
        """,
        {"now": now, "club": club_id, "ind": is_individual},
    )


async def _cleanup_tournament(tournament_id: int) -> None:
    """FK-safe teardown for everything a tournament may own here."""
    await database.execute(
        "DELETE FROM tournament_scorers WHERE tournament_id = :t", {"t": tournament_id}
    )
    await database.execute(
        """
        DELETE FROM stage_item_inputs WHERE stage_item_id IN (
            SELECT si.id FROM stage_items si
            JOIN stages s ON si.stage_id = s.id WHERE s.tournament_id = :t
        )
        """,
        {"t": tournament_id},
    )
    await database.execute(
        """
        DELETE FROM matches WHERE round_id IN (
            SELECT r.id FROM rounds r
            JOIN stage_items si ON r.stage_item_id = si.id
            JOIN stages s ON si.stage_id = s.id WHERE s.tournament_id = :t
        )
        """,
        {"t": tournament_id},
    )
    await database.execute(
        """
        DELETE FROM rounds WHERE stage_item_id IN (
            SELECT si.id FROM stage_items si
            JOIN stages s ON si.stage_id = s.id WHERE s.tournament_id = :t
        )
        """,
        {"t": tournament_id},
    )
    await database.execute(
        """
        DELETE FROM stage_items WHERE stage_id IN (
            SELECT id FROM stages WHERE tournament_id = :t
        )
        """,
        {"t": tournament_id},
    )
    await database.execute("DELETE FROM stages WHERE tournament_id = :t", {"t": tournament_id})
    await database.execute(
        """
        DELETE FROM players_x_teams WHERE team_id IN (
            SELECT id FROM teams WHERE tournament_id = :t
        )
        """,
        {"t": tournament_id},
    )
    await database.execute(
        "DELETE FROM teams_x_users WHERE tournament_id = :t", {"t": tournament_id}
    )
    await database.execute("DELETE FROM players WHERE tournament_id = :t", {"t": tournament_id})
    await database.execute("DELETE FROM teams WHERE tournament_id = :t", {"t": tournament_id})
    await database.execute("DELETE FROM rankings WHERE tournament_id = :t", {"t": tournament_id})
    await database.execute("DELETE FROM tournaments WHERE id = :t", {"t": tournament_id})


@pytest_asyncio.fixture(loop_scope="session")
async def individual_tournament(auth_context: AuthContext) -> AsyncIterator[int]:
    """An empty individual tournament under the session owner's club."""
    tid = await _make_tournament(auth_context.club.id)
    try:
        yield tid
    finally:
        await _cleanup_tournament(tid)


async def _add_match(tournament_id: int) -> None:
    """Create the minimal stage/stage_item/round/match chain so
    ``tournament_has_matches`` is True (play has started)."""
    ranking_id = await _insert(
        "INSERT INTO rankings "
        "(tournament_id, position, win_points, draw_points, loss_points, add_score_points) "
        "VALUES (:t, 0, 1, 0.5, 0, true)",
        {"t": tournament_id},
    )
    stage_id = await _insert(
        "INSERT INTO stages (name, tournament_id, is_active) VALUES ('S', :t, true)",
        {"t": tournament_id},
    )
    stage_item_id = await _insert(
        "INSERT INTO stage_items (name, stage_id, team_count, ranking_id, type) "
        "VALUES ('SI', :s, 0, :r, 'ROUND_ROBIN')",
        {"s": stage_id, "r": ranking_id},
    )
    round_id = await _insert(
        "INSERT INTO rounds (name, is_draft, stage_item_id) VALUES ('R', false, :si)",
        {"si": stage_item_id},
    )
    await database.execute(
        """
        INSERT INTO matches
            (round_id, stage_item_input1_conflict, stage_item_input2_conflict,
             stage_item_input1_score, stage_item_input2_score)
        VALUES (:r, false, false, 0, 0)
        """,
        {"r": round_id},
    )


# --- request_to_join ---


@pytest.mark.asyncio(loop_scope="session")
async def test_join_happy_direct(auth_context: AuthContext, individual_tournament: int) -> None:
    user_id, _, headers = await _make_user("Joiner")
    res = await send_request(
        HTTPMethod.POST,
        f"tournaments/{individual_tournament}/join-requests",
        json={},
        headers=headers,
    )
    assert res == SUCCESS_RESPONSE

    bound = await database.fetch_val(
        "SELECT EXISTS(SELECT 1 FROM teams_x_users WHERE tournament_id = :t AND user_id = :u)",
        {"t": individual_tournament, "u": user_id},
    )
    assert bool(bound) is True

    # Second attempt -> already participate.
    res2 = await send_request(
        HTTPMethod.POST,
        f"tournaments/{individual_tournament}/join-requests",
        json={},
        headers=headers,
    )
    assert "已报名" in res2["detail"]

    await database.execute("DELETE FROM users WHERE id = :u", {"u": user_id})


@pytest.mark.asyncio(loop_scope="session")
async def test_join_trust_creator_adds_owner_as_manager(
    auth_context: AuthContext, individual_tournament: int
) -> None:
    user_id, _, headers = await _make_user("Truster")
    res = await send_request(
        HTTPMethod.POST,
        f"tournaments/{individual_tournament}/join-requests",
        json={"trust_creator": True},
        headers=headers,
    )
    assert res == SUCCESS_RESPONSE

    trusts_owner = await database.fetch_val(
        "SELECT EXISTS(SELECT 1 FROM user_trusted_managers WHERE user_id = :u AND manager_id = :m)",
        {"u": user_id, "m": auth_context.user.id},
    )
    assert bool(trusts_owner) is True

    await database.execute("DELETE FROM user_trusted_managers WHERE user_id = :u", {"u": user_id})
    await database.execute("DELETE FROM users WHERE id = :u", {"u": user_id})


@pytest.mark.asyncio(loop_scope="session")
async def test_join_rejects_non_individual(auth_context: AuthContext) -> None:
    tid = await _make_tournament(auth_context.club.id, is_individual=False)
    _, _, headers = await _make_user("X")
    try:
        res = await send_request(
            HTTPMethod.POST,
            f"tournaments/{tid}/join-requests",
            json={},
            headers=headers,
        )
        assert "只有个人赛" in res["detail"]
    finally:
        await _cleanup_tournament(tid)
        await database.execute(
            "DELETE FROM users WHERE email LIKE 'partapi_%' AND id NOT IN "
            "(SELECT user_id FROM users_x_clubs)",
            {},
        )


@pytest.mark.asyncio(loop_scope="session")
async def test_join_rejects_settled(auth_context: AuthContext) -> None:
    tid = await _make_tournament(auth_context.club.id)
    await database.execute("UPDATE tournaments SET settled_seq = 1 WHERE id = :t", {"t": tid})
    user_id, _, headers = await _make_user("X")
    try:
        res = await send_request(
            HTTPMethod.POST,
            f"tournaments/{tid}/join-requests",
            json={},
            headers=headers,
        )
        assert "已结算" in res["detail"]
    finally:
        await _cleanup_tournament(tid)
        await database.execute("DELETE FROM users WHERE id = :u", {"u": user_id})


@pytest.mark.asyncio(loop_scope="session")
async def test_join_rejects_started(auth_context: AuthContext, individual_tournament: int) -> None:
    await _add_match(individual_tournament)
    user_id, _, headers = await _make_user("X")
    try:
        res = await send_request(
            HTTPMethod.POST,
            f"tournaments/{individual_tournament}/join-requests",
            json={},
            headers=headers,
        )
        assert "比赛已开始" in res["detail"]
    finally:
        await database.execute("DELETE FROM users WHERE id = :u", {"u": user_id})


@pytest.mark.asyncio(loop_scope="session")
async def test_join_rejects_expired_day(
    auth_context: AuthContext, individual_tournament: int
) -> None:
    """A tournament dated before today is closed for signups (same-day stays open)
    and disappears from the joinable list."""
    await database.execute(
        "UPDATE tournaments SET start_time = NOW() - INTERVAL '2 days' WHERE id = :t",
        {"t": individual_tournament},
    )
    user_id, _, headers = await _make_user("Late")
    try:
        res = await send_request(
            HTTPMethod.POST,
            f"tournaments/{individual_tournament}/join-requests",
            json={},
            headers=headers,
        )
        assert "比赛日期已过" in res["detail"]

        joinable = await send_request(HTTPMethod.GET, "me/joinable-tournaments", headers=headers)
        assert individual_tournament not in [t["id"] for t in joinable["data"]]

        # Same-day (start of today) stays open.
        await database.execute(
            "UPDATE tournaments SET start_time = date_trunc('day', NOW()) WHERE id = :t",
            {"t": individual_tournament},
        )
        joinable = await send_request(HTTPMethod.GET, "me/joinable-tournaments", headers=headers)
        assert individual_tournament in [t["id"] for t in joinable["data"]]
    finally:
        await database.execute(
            "UPDATE tournaments SET start_time = NOW() WHERE id = :t", {"t": individual_tournament}
        )
        await database.execute("DELETE FROM users WHERE id = :u", {"u": user_id})


# --- leave_tournament ---


@pytest.mark.asyncio(loop_scope="session")
async def test_leave_happy(auth_context: AuthContext, individual_tournament: int) -> None:
    user_id, _, headers = await _make_user("Leaver")
    await send_request(
        HTTPMethod.POST,
        f"tournaments/{individual_tournament}/join-requests",
        json={},
        headers=headers,
    )
    res = await send_request(
        HTTPMethod.POST,
        f"tournaments/{individual_tournament}/leave",
        headers=headers,
    )
    assert res == SUCCESS_RESPONSE

    still_bound = await database.fetch_val(
        "SELECT EXISTS(SELECT 1 FROM teams_x_users WHERE tournament_id = :t AND user_id = :u)",
        {"t": individual_tournament, "u": user_id},
    )
    assert bool(still_bound) is False

    # Joining creates a player alongside the team; leaving must take it with it.
    leftover_players = await database.fetch_val(
        "SELECT count(*) FROM players WHERE tournament_id = :t", {"t": individual_tournament}
    )
    assert leftover_players == 0

    await database.execute("DELETE FROM users WHERE id = :u", {"u": user_id})


@pytest.mark.asyncio(loop_scope="session")
async def test_leave_not_participant(auth_context: AuthContext, individual_tournament: int) -> None:
    user_id, _, headers = await _make_user("NotIn")
    try:
        res = await send_request(
            HTTPMethod.POST,
            f"tournaments/{individual_tournament}/leave",
            headers=headers,
        )
        assert "你尚未参加" in res["detail"]
    finally:
        await database.execute("DELETE FROM users WHERE id = :u", {"u": user_id})


@pytest.mark.asyncio(loop_scope="session")
async def test_leave_rejects_non_individual(auth_context: AuthContext) -> None:
    tid = await _make_tournament(auth_context.club.id, is_individual=False)
    user_id, _, headers = await _make_user("X")
    try:
        res = await send_request(HTTPMethod.POST, f"tournaments/{tid}/leave", headers=headers)
        assert "只有个人赛" in res["detail"]
    finally:
        await _cleanup_tournament(tid)
        await database.execute("DELETE FROM users WHERE id = :u", {"u": user_id})


@pytest.mark.asyncio(loop_scope="session")
async def test_leave_rejects_settled(auth_context: AuthContext) -> None:
    tid = await _make_tournament(auth_context.club.id)
    await database.execute("UPDATE tournaments SET settled_seq = 1 WHERE id = :t", {"t": tid})
    user_id, _, headers = await _make_user("X")
    try:
        res = await send_request(HTTPMethod.POST, f"tournaments/{tid}/leave", headers=headers)
        assert "赛事已结算" in res["detail"]
    finally:
        await _cleanup_tournament(tid)
        await database.execute("DELETE FROM users WHERE id = :u", {"u": user_id})


@pytest.mark.asyncio(loop_scope="session")
async def test_leave_rejects_started(auth_context: AuthContext, individual_tournament: int) -> None:
    user_id, _, headers = await _make_user("X")
    await send_request(
        HTTPMethod.POST,
        f"tournaments/{individual_tournament}/join-requests",
        json={},
        headers=headers,
    )
    await _add_match(individual_tournament)
    try:
        res = await send_request(
            HTTPMethod.POST,
            f"tournaments/{individual_tournament}/leave",
            headers=headers,
        )
        assert "比赛已开始" in res["detail"]
    finally:
        await database.execute("DELETE FROM users WHERE id = :u", {"u": user_id})


@pytest.mark.asyncio(loop_scope="session")
async def test_leave_fk_violation_when_placed_in_stage(
    auth_context: AuthContext, individual_tournament: int
) -> None:
    """The user's team is placed into a stage_item_input; leaving would orphan it,
    so a clean 400 surfaces instead of a 500."""
    user_id, _, headers = await _make_user("Placed")
    await send_request(
        HTTPMethod.POST,
        f"tournaments/{individual_tournament}/join-requests",
        json={},
        headers=headers,
    )
    team_id = await database.fetch_val(
        "SELECT team_id FROM teams_x_users WHERE tournament_id = :t AND user_id = :u",
        {"t": individual_tournament, "u": user_id},
    )
    ranking_id = await _insert(
        "INSERT INTO rankings "
        "(tournament_id, position, win_points, draw_points, loss_points, add_score_points) "
        "VALUES (:t, 0, 1, 0.5, 0, true)",
        {"t": individual_tournament},
    )
    stage_id = await _insert(
        "INSERT INTO stages (name, tournament_id, is_active) VALUES ('S', :t, true)",
        {"t": individual_tournament},
    )
    stage_item_id = await _insert(
        "INSERT INTO stage_items (name, stage_id, team_count, ranking_id, type) "
        "VALUES ('SI', :s, 1, :r, 'ROUND_ROBIN')",
        {"s": stage_id, "r": ranking_id},
    )
    await database.execute(
        "INSERT INTO stage_item_inputs (slot, tournament_id, stage_item_id, team_id) "
        "VALUES (0, :t, :si, :tm)",
        {"t": individual_tournament, "si": stage_item_id, "tm": team_id},
    )
    try:
        res = await send_request(
            HTTPMethod.POST,
            f"tournaments/{individual_tournament}/leave",
            headers=headers,
        )
        # FK violation surfaces as a 400 (caught), not a 500.
        assert "detail" in res
    finally:
        await database.execute("DELETE FROM users WHERE id = :u", {"u": user_id})


# --- my_join_status ---


@pytest.mark.asyncio(loop_scope="session")
async def test_my_join_status_participant_vs_not(
    auth_context: AuthContext, individual_tournament: int
) -> None:
    user_id, _, headers = await _make_user("Status")

    # Non-participant: can_join True, can_leave False.
    res = await send_request(
        HTTPMethod.GET,
        f"tournaments/{individual_tournament}/my-join-status",
        headers=headers,
    )
    data = res["data"]
    assert data["is_participant"] is False
    assert data["can_join"] is True
    assert data["can_leave"] is False
    assert data["can_manage"] is False
    assert data["can_record"] is False

    # After joining: participant -> can_leave True, can_join False.
    await send_request(
        HTTPMethod.POST,
        f"tournaments/{individual_tournament}/join-requests",
        json={},
        headers=headers,
    )
    res2 = await send_request(
        HTTPMethod.GET,
        f"tournaments/{individual_tournament}/my-join-status",
        headers=headers,
    )
    data2 = res2["data"]
    assert data2["is_participant"] is True
    assert data2["can_join"] is False
    assert data2["can_leave"] is True

    await database.execute("DELETE FROM users WHERE id = :u", {"u": user_id})


@pytest.mark.asyncio(loop_scope="session")
async def test_my_join_status_owner_can_manage(
    auth_context: AuthContext, individual_tournament: int
) -> None:
    res = await send_request(
        HTTPMethod.GET,
        f"tournaments/{individual_tournament}/my-join-status",
        headers=auth_context.headers,
    )
    assert res["data"]["can_manage"] is True


@pytest.mark.asyncio(loop_scope="session")
async def test_my_join_status_window_closed_when_started(
    auth_context: AuthContext, individual_tournament: int
) -> None:
    user_id, _, headers = await _make_user("Closed")
    await _add_match(individual_tournament)
    try:
        res = await send_request(
            HTTPMethod.GET,
            f"tournaments/{individual_tournament}/my-join-status",
            headers=headers,
        )
        # Started -> open_window False -> neither join nor leave offered.
        assert res["data"]["can_join"] is False
        assert res["data"]["can_leave"] is False
    finally:
        await database.execute("DELETE FROM users WHERE id = :u", {"u": user_id})


# --- addable participants + add_participant ---


@pytest.mark.asyncio(loop_scope="session")
async def test_addable_participants_lists_owner_and_trusters(
    auth_context: AuthContext, individual_tournament: int
) -> None:
    # A user who trusts the club owner -> appears as addable.
    truster_id, truster_email, _ = await _make_user("Truster")
    await database.execute(
        "INSERT INTO user_trusted_managers (user_id, manager_id, created) VALUES (:u, :m, :now)",
        {"u": truster_id, "m": auth_context.user.id, "now": datetime_utc.now()},
    )
    # A bound user -> excluded.
    bound_id, _, bound_headers = await _make_user("Bound")
    await send_request(
        HTTPMethod.POST,
        f"tournaments/{individual_tournament}/join-requests",
        json={},
        headers=bound_headers,
    )
    try:
        res = await send_request(
            HTTPMethod.GET,
            f"tournaments/{individual_tournament}/addable-participants",
            headers=auth_context.headers,
        )
        ids = {row["user_id"] for row in res["data"]}
        # The owner themselves is addable, and the truster is addable.
        assert auth_context.user.id in ids
        assert truster_id in ids
        # The already-bound account is excluded.
        assert bound_id not in ids
    finally:
        await database.execute(
            "DELETE FROM user_trusted_managers WHERE user_id = :u", {"u": truster_id}
        )
        await database.execute("DELETE FROM users WHERE id = :u", {"u": truster_id})
        await database.execute("DELETE FROM users WHERE id = :u", {"u": bound_id})


@pytest.mark.asyncio(loop_scope="session")
async def test_addable_participants_rejects_non_individual(auth_context: AuthContext) -> None:
    tid = await _make_tournament(auth_context.club.id, is_individual=False)
    try:
        res = await send_request(
            HTTPMethod.GET,
            f"tournaments/{tid}/addable-participants",
            headers=auth_context.headers,
        )
        assert "只有个人赛" in res["detail"]
    finally:
        await _cleanup_tournament(tid)


@pytest.mark.asyncio(loop_scope="session")
async def test_addable_participants_rejects_settled(auth_context: AuthContext) -> None:
    tid = await _make_tournament(auth_context.club.id)
    await database.execute("UPDATE tournaments SET settled_seq = 1 WHERE id = :t", {"t": tid})
    try:
        res = await send_request(
            HTTPMethod.GET,
            f"tournaments/{tid}/addable-participants",
            headers=auth_context.headers,
        )
        assert "已结算" in res["detail"]
    finally:
        await _cleanup_tournament(tid)


@pytest.mark.asyncio(loop_scope="session")
async def test_add_participant_owner_self_happy(
    auth_context: AuthContext, individual_tournament: int
) -> None:
    res = await send_request(
        HTTPMethod.POST,
        f"tournaments/{individual_tournament}/participants",
        json={"user_id": auth_context.user.id},
        headers=auth_context.headers,
    )
    assert res == SUCCESS_RESPONSE

    bound = await database.fetch_val(
        "SELECT EXISTS(SELECT 1 FROM teams_x_users WHERE tournament_id = :t AND user_id = :u)",
        {"t": individual_tournament, "u": auth_context.user.id},
    )
    assert bool(bound) is True

    # Adding again -> already participates.
    res2 = await send_request(
        HTTPMethod.POST,
        f"tournaments/{individual_tournament}/participants",
        json={"user_id": auth_context.user.id},
        headers=auth_context.headers,
    )
    assert "已参加" in res2["detail"]


@pytest.mark.asyncio(loop_scope="session")
async def test_add_participant_requires_trust(
    auth_context: AuthContext, individual_tournament: int
) -> None:
    target_id, _, _ = await _make_user("Untrusting")
    try:
        # Target has not trusted the owner -> 403.
        res = await send_request(
            HTTPMethod.POST,
            f"tournaments/{individual_tournament}/participants",
            json={"user_id": target_id},
            headers=auth_context.headers,
        )
        assert "未授权" in res["detail"]

        # Now the target trusts the owner -> direct add succeeds.
        await database.execute(
            "INSERT INTO user_trusted_managers (user_id, manager_id, created) "
            "VALUES (:u, :m, :now)",
            {"u": target_id, "m": auth_context.user.id, "now": datetime_utc.now()},
        )
        res2 = await send_request(
            HTTPMethod.POST,
            f"tournaments/{individual_tournament}/participants",
            json={"user_id": target_id},
            headers=auth_context.headers,
        )
        assert res2 == SUCCESS_RESPONSE
    finally:
        await database.execute(
            "DELETE FROM user_trusted_managers WHERE user_id = :u", {"u": target_id}
        )
        await database.execute("DELETE FROM users WHERE id = :u", {"u": target_id})


@pytest.mark.asyncio(loop_scope="session")
async def test_add_participant_admin_bypasses_trust(
    auth_context: AuthContext, individual_tournament: int
) -> None:
    """A site admin who manages the tournament may add anyone without per-user
    trust, and their addable-participants picker lists every non-demo account."""
    target_id, _, _ = await _make_user("NoTrustTarget")
    demo_email = f"partapi_{generate_email()}"
    demo_id = await _insert(
        "INSERT INTO users (email, name, password_hash, account_type) "
        "VALUES (:e, 'PartApiDemo', 'x', 'DEMO')",
        {"e": demo_email},
    )
    await database.execute(
        "UPDATE users SET is_admin = true WHERE id = :u", {"u": auth_context.user.id}
    )
    try:
        res = await send_request(
            HTTPMethod.GET,
            f"tournaments/{individual_tournament}/addable-participants",
            headers=auth_context.headers,
        )
        ids = {row["user_id"] for row in res["data"]}
        # No trust row exists, yet the target is offered; demo accounts are not.
        assert target_id in ids
        assert demo_id not in ids

        res2 = await send_request(
            HTTPMethod.POST,
            f"tournaments/{individual_tournament}/participants",
            json={"user_id": target_id},
            headers=auth_context.headers,
        )
        assert res2 == SUCCESS_RESPONSE
    finally:
        await database.execute(
            "UPDATE users SET is_admin = false WHERE id = :u", {"u": auth_context.user.id}
        )
        await database.execute(
            "DELETE FROM teams_x_users WHERE tournament_id = :t AND user_id = :u",
            {"t": individual_tournament, "u": target_id},
        )
        await database.execute("DELETE FROM users WHERE id = :u", {"u": target_id})
        await database.execute("DELETE FROM users WHERE id = :u", {"u": demo_id})


# --- trusted managers (me) ---


@pytest.mark.asyncio(loop_scope="session")
async def test_trusted_managers_crud(auth_context: AuthContext) -> None:
    manager_id, manager_email, _ = await _make_user("Manager")
    try:
        # Initially empty for this account (the owner has trusted nobody yet).
        res = await send_auth_request(HTTPMethod.GET, "me/trusted-managers", auth_context)
        assert manager_id not in {m["manager_id"] for m in res["data"]}

        # Add by email.
        add = await send_auth_request(
            HTTPMethod.POST,
            "me/trusted-managers",
            auth_context,
            json={"manager_email": manager_email},
        )
        assert add == SUCCESS_RESPONSE

        res2 = await send_auth_request(HTTPMethod.GET, "me/trusted-managers", auth_context)
        assert manager_id in {m["manager_id"] for m in res2["data"]}

        # 404 unknown email.
        missing = await send_auth_request(
            HTTPMethod.POST,
            "me/trusted-managers",
            auth_context,
            json={"manager_email": "partapi_nope@nowhere"},
        )
        assert "没有找到该邮箱或名称" in missing["detail"]

        # 400 cannot add yourself.
        myself = await send_auth_request(
            HTTPMethod.POST,
            "me/trusted-managers",
            auth_context,
            json={"manager_email": auth_context.user.email},
        )
        assert "不能添加自己" in myself["detail"]

        # Delete.
        delete = await send_auth_request(
            HTTPMethod.DELETE, f"me/trusted-managers/{manager_id}", auth_context
        )
        assert delete == SUCCESS_RESPONSE
        res3 = await send_auth_request(HTTPMethod.GET, "me/trusted-managers", auth_context)
        assert manager_id not in {m["manager_id"] for m in res3["data"]}
    finally:
        await database.execute(
            "DELETE FROM user_trusted_managers WHERE user_id = :u OR manager_id = :u",
            {"u": auth_context.user.id},
        )
        await database.execute("DELETE FROM users WHERE id = :u", {"u": manager_id})


# --- admit_user_to_tournament (logic) defensive branch ---


@pytest.mark.asyncio(loop_scope="session")
async def test_admit_unknown_user_raises(
    auth_context: AuthContext, individual_tournament: int
) -> None:
    tournament = await sql_get_tournament(individual_tournament)
    with pytest.raises(ValueError, match="User not found"):
        await admit_user_to_tournament(tournament, UserId(2_000_000_000))


# --- scorers ---


@pytest.mark.asyncio(loop_scope="session")
async def test_scorers_crud(auth_context: AuthContext, individual_tournament: int) -> None:
    scorer_id, scorer_email, _ = await _make_user("Scorer")
    try:
        # Empty list initially.
        res = await send_request(
            HTTPMethod.GET,
            f"tournaments/{individual_tournament}/scorers",
            headers=auth_context.headers,
        )
        assert res["data"] == []

        # Add by email.
        add = await send_request(
            HTTPMethod.POST,
            f"tournaments/{individual_tournament}/scorers",
            json={"user_email": scorer_email},
            headers=auth_context.headers,
        )
        assert add == SUCCESS_RESPONSE

        res2 = await send_request(
            HTTPMethod.GET,
            f"tournaments/{individual_tournament}/scorers",
            headers=auth_context.headers,
        )
        assert scorer_id in {s["user_id"] for s in res2["data"]}

        # 404 unknown email.
        missing = await send_request(
            HTTPMethod.POST,
            f"tournaments/{individual_tournament}/scorers",
            json={"user_email": "partapi_nobody@nowhere"},
            headers=auth_context.headers,
        )
        assert "没有找到该邮箱或名称" in missing["detail"]

        # Delete.
        delete = await send_request(
            HTTPMethod.DELETE,
            f"tournaments/{individual_tournament}/scorers/{scorer_id}",
            headers=auth_context.headers,
        )
        assert delete == SUCCESS_RESPONSE
        res3 = await send_request(
            HTTPMethod.GET,
            f"tournaments/{individual_tournament}/scorers",
            headers=auth_context.headers,
        )
        assert scorer_id not in {s["user_id"] for s in res3["data"]}
    finally:
        await database.execute(
            "DELETE FROM tournament_scorers WHERE user_id = :u", {"u": scorer_id}
        )
        await database.execute("DELETE FROM users WHERE id = :u", {"u": scorer_id})


@pytest.mark.asyncio(loop_scope="session")
async def test_add_scorer_by_name_with_stored_whitespace(
    auth_context: AuthContext, individual_tournament: int
) -> None:
    """Legacy rows were stored with a padded name ("Jenny "), which made the
    account unfindable by the name its owner actually types."""
    scorer_id, _, _ = await _make_user("PartAPI Padded ")
    try:
        add = await send_request(
            HTTPMethod.POST,
            f"tournaments/{individual_tournament}/scorers",
            json={"user_email": "PartAPI Padded"},
            headers=auth_context.headers,
        )
        assert add == SUCCESS_RESPONSE

        res = await send_request(
            HTTPMethod.GET,
            f"tournaments/{individual_tournament}/scorers",
            headers=auth_context.headers,
        )
        assert scorer_id in {s["user_id"] for s in res["data"]}
    finally:
        await database.execute(
            "DELETE FROM tournament_scorers WHERE user_id = :u", {"u": scorer_id}
        )
        await database.execute("DELETE FROM users WHERE id = :u", {"u": scorer_id})
