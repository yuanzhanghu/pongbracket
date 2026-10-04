"""End-to-end settlement test against a real Postgres test DB.

Builds the minimal tournament structure (club, individual+rated tournament, two
accounts, two bound teams, one non-draft round with a decided match) and verifies
the ChinaTT batch settlement writes the ledger and updates current ratings.
"""

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from heliclockter import datetime_utc

from bracket.database import database
from bracket.logic.rating.settlement import SettlementError, settle_tournament
from bracket.models.db.rating import SettlementStatus
from bracket.sql.participants import tournament_has_matches
from bracket.sql.ratings import (
    approve_player_rating,
    clear_settlement_requested,
    count_unrated_participants,
    get_pending_rating_ids_for_tournament,
    get_settlement_review_queue,
    mark_settlement_requested,
)
from bracket.sql.teams import get_teams_with_members
from bracket.sql.tournaments import sql_get_tournament


async def _insert(query: str, values: dict) -> int:
    return await database.fetch_val(query + " RETURNING id", values)


@pytest_asyncio.fixture(loop_scope="session")
async def rated_tournament(reinit_database) -> AsyncIterator[dict]:
    now = datetime_utc.now()
    ids: dict = {}
    try:
        ids["category"] = await _insert(
            "INSERT INTO rating_categories (key, name, algorithm) VALUES (:k, :n, 'chinatt')",
            {"k": "TEST_CAT", "n": "Test Category"},
        )
        ids["club"] = await _insert("INSERT INTO clubs (name) VALUES ('C')", {})
        ids["tournament"] = await _insert(
            """
            INSERT INTO tournaments
                (name, start_time, club_id, dashboard_public, is_individual, rating_category_id)
            VALUES ('T', :now, :club, true, true, :cat)
            """,
            {"now": now, "club": ids["club"], "cat": ids["category"]},
        )
        ids["userA"] = await _insert(
            "INSERT INTO users (email, name, password_hash, account_type) "
            "VALUES (:e, 'Alice', 'x', 'REGULAR')",
            {"e": "alice@test"},
        )
        ids["userB"] = await _insert(
            "INSERT INTO users (email, name, password_hash, account_type) "
            "VALUES (:e, 'Bob', 'x', 'REGULAR')",
            {"e": "bob@test"},
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
        # FK-safe teardown order.
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
            ("clubs", "id", "club"),
            ("rating_categories", "id", "category"),
        ]:
            if key in ids:
                await database.execute(f"DELETE FROM {table} WHERE {col} = :v", {"v": ids[key]})


@pytest.mark.asyncio(loop_scope="session")
async def test_settle_happy_path(reinit_database, rated_tournament: dict) -> None:
    ids = rated_tournament
    tournament = await sql_get_tournament(ids["tournament"])
    result = await settle_tournament(tournament)

    assert result.status is SettlementStatus.SETTLED
    assert result.settled_seq == 1

    ratings = {
        r["user_id"]: r["current_rating"]
        for r in await database.fetch_all(
            "SELECT user_id, current_rating FROM player_ratings WHERE category_id = :c",
            {"c": ids["category"]},
        )
    }
    # diff 50 (bin 38-62), higher-rated (Alice 1500) wins -> +6 / -6.
    assert ratings[ids["userA"]] == 1506
    assert ratings[ids["userB"]] == 1444

    events = await database.fetch_all(
        "SELECT result, delta FROM rating_events WHERE tournament_id = :t ORDER BY delta DESC",
        {"t": ids["tournament"]},
    )
    assert [(e["result"], e["delta"]) for e in events] == [("W", 6), ("L", -6)]

    settled = await sql_get_tournament(ids["tournament"])
    assert settled.settled_seq == 1
    assert settled.settled_at is not None

    # The team rows expose the ledger's pre/post ratings for the participants tab.
    teams = {t.bound_user_id: t for t in await get_teams_with_members(ids["tournament"])}
    assert teams[ids["userA"]].settled_pre_rating == 1500
    assert teams[ids["userA"]].settled_post_rating == 1506
    assert teams[ids["userB"]].settled_pre_rating == 1450
    assert teams[ids["userB"]].settled_post_rating == 1444

    # Sequential semantics regression: settlement writes cumulative ledger rows
    # (each match uses the immediate rating), so the pre-event rating is the
    # FIRST row's rating_before and the settled rating is the LAST row's
    # rating_after — even when the rating dips below the entry rating
    # mid-tournament (MIN(rating_before) would wrongly pick the dip).
    for before, after, delta, result in [
        (1506, 1494, -12, "L"),  # dips below the 1500 entry rating
        (1494, 1502, 8, "W"),
    ]:
        await database.execute(
            """
            INSERT INTO rating_events
                (category_id, match_id, user_id, opponent_id, tournament_id,
                 rating_before, rating_after, delta, result, created)
            VALUES (:c, :m, :u, :o, :t, :rb, :ra, :d, :res, NOW())
            """,
            {
                "c": ids["category"],
                "m": ids["match"],
                "u": ids["userA"],
                "o": ids["userB"],
                "t": ids["tournament"],
                "rb": before,
                "ra": after,
                "d": delta,
                "res": result,
            },
        )
    teams = {t.bound_user_id: t for t in await get_teams_with_members(ids["tournament"])}
    assert teams[ids["userA"]].settled_pre_rating == 1500
    assert teams[ids["userA"]].settled_post_rating == 1502


@pytest.mark.asyncio(loop_scope="session")
async def test_settle_blocks_on_unrecorded_match(reinit_database, rated_tournament: dict) -> None:
    ids = rated_tournament
    await database.execute(
        "UPDATE matches SET stage_item_input1_score = 0, stage_item_input2_score = 0 WHERE id = :m",
        {"m": ids["match"]},
    )
    tournament = await sql_get_tournament(ids["tournament"])
    with pytest.raises(SettlementError, match="没有录入结果"):
        await settle_tournament(tournament)


@pytest.mark.asyncio(loop_scope="session")
async def test_settle_blocks_on_unbound_team(reinit_database, rated_tournament: dict) -> None:
    ids = rated_tournament
    await database.execute("DELETE FROM teams_x_users WHERE team_id = :tm", {"tm": ids["teamB"]})
    tournament = await sql_get_tournament(ids["tournament"])
    with pytest.raises(SettlementError, match="未绑定账号"):
        await settle_tournament(tournament)


@pytest.mark.asyncio(loop_scope="session")
async def test_teams_carry_rating_and_unrated_count(
    reinit_database, rated_tournament: dict
) -> None:
    ids = rated_tournament
    teams = await get_teams_with_members(ids["tournament"])
    by_user = {t.bound_user_id: t for t in teams}
    # The fixture seeds Alice ACTIVE @1500; the team row carries it.
    assert by_user[ids["userA"]].rating == 1500
    assert by_user[ids["userA"]].rating_status == "ACTIVE"

    # All participants rated -> nothing blocks starting.
    assert await count_unrated_participants(ids["tournament"], ids["category"]) == 0

    # Drop one rating -> one unrated participant; its team row reports no rating.
    await database.execute(
        "DELETE FROM player_ratings WHERE category_id = :c AND user_id = :u",
        {"c": ids["category"], "u": ids["userB"]},
    )
    assert await count_unrated_participants(ids["tournament"], ids["category"]) == 1
    teams2 = {t.bound_user_id: t for t in await get_teams_with_members(ids["tournament"])}
    assert teams2[ids["userB"]].rating is None
    assert teams2[ids["userB"]].rating_status is None


@pytest.mark.asyncio(loop_scope="session")
async def test_tournament_with_match_reports_started(
    reinit_database, rated_tournament: dict
) -> None:
    # The fixture builds a real match, so play has started.
    assert await tournament_has_matches(rated_tournament["tournament"]) is True


@pytest.mark.asyncio(loop_scope="session")
async def test_approve_and_settle_one_button(reinit_database, rated_tournament: dict) -> None:
    """The owner requests settlement once while seeds are PENDING; the admin then
    approves (with an adjustment) and settles in a single pass."""
    ids = rated_tournament
    # Flip both seeds back to PENDING (the fixture seeds them ACTIVE).
    await database.execute(
        "UPDATE player_ratings SET status = 'PENDING' WHERE category_id = :c",
        {"c": ids["category"]},
    )

    tournament = await sql_get_tournament(ids["tournament"])

    # Owner's single request: blocked on review, parked in the admin queue.
    result = await settle_tournament(tournament)
    assert result.status is SettlementStatus.PENDING_REVIEW
    assert result.pending_review_count == 2
    await mark_settlement_requested(ids["tournament"])

    queue = await get_settlement_review_queue()
    mine = [q for q in queue if q.tournament_id == ids["tournament"]]
    assert len(mine) == 1
    assert len(mine[0].players) == 2

    # Admin approves; Alice's seed is adjusted up to 1600, Bob keeps 1450.
    pending_ids = await get_pending_rating_ids_for_tournament(ids["tournament"], ids["category"])
    assert len(pending_ids) == 2
    admin_id = ids["userA"]  # any user id; FK only needs to exist
    alice_pr = await database.fetch_val(
        "SELECT id FROM player_ratings WHERE category_id = :c AND user_id = :u",
        {"c": ids["category"], "u": ids["userA"]},
    )
    for prid in pending_ids:
        adjusted = 1600 if prid == alice_pr else None
        await approve_player_rating(prid, admin_id, adjusted)

    settled = await sql_get_tournament(ids["tournament"])
    result2 = await settle_tournament(settled)
    assert result2.status is SettlementStatus.SETTLED
    await clear_settlement_requested(ids["tournament"])

    rows = {
        r["user_id"]: r
        for r in await database.fetch_all(
            "SELECT user_id, initial_rating, current_rating, status "
            "FROM player_ratings WHERE category_id = :c",
            {"c": ids["category"]},
        )
    }
    # Adjustment applied and now ACTIVE.
    assert rows[ids["userA"]]["initial_rating"] == 1600
    assert rows[ids["userA"]]["status"] == "ACTIVE"
    assert rows[ids["userB"]]["status"] == "ACTIVE"
    # Alice (1600) beat Bob (1450) 3-1: zero-sum exchange off the adjusted entry.
    gain = rows[ids["userA"]]["current_rating"] - 1600
    assert gain > 0
    assert rows[ids["userB"]]["current_rating"] == 1450 - gain
    # The queue is empty once settled.
    assert all(q.tournament_id != ids["tournament"] for q in await get_settlement_review_queue())


@pytest.mark.asyncio(loop_scope="session")
async def test_double_settle_is_rejected(reinit_database, rated_tournament: dict) -> None:
    ids = rated_tournament
    tournament = await sql_get_tournament(ids["tournament"])
    await settle_tournament(tournament)
    tournament2 = await sql_get_tournament(ids["tournament"])
    with pytest.raises(SettlementError, match="已经结算"):
        await settle_tournament(tournament2)
