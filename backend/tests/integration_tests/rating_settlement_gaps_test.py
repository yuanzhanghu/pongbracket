"""Extra settlement coverage: edge branches of bracket.logic.rating.settlement
not exercised by rating_settlement_test.py.

Reuses the same minimal-tournament builder shape; rows are torn down FK-safely.
"""

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from heliclockter import datetime_utc

from bracket.database import database
from bracket.logic.rating.settlement import (
    SettlementError,
    _active_stage_is_last,
    _player_rating_status,
    settle_tournament,
    validate_settlement_ready,
)
from bracket.models.db.rating import SettlementStatus
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
            {"k": "GAPS_CAT", "n": "Gaps Category"},
        )
        ids["club"] = await _insert("INSERT INTO clubs (name) VALUES ('GapsClub')", {})
        ids["tournament"] = await _insert(
            """
            INSERT INTO tournaments
                (name, start_time, club_id, dashboard_public, is_individual, rating_category_id)
            VALUES ('GapsT', :now, :club, true, true, :cat)
            """,
            {"now": now, "club": ids["club"], "cat": ids["category"]},
        )
        ids["userA"] = await _insert(
            "INSERT INTO users (email, name, password_hash, account_type) "
            "VALUES (:e, 'AliceGaps', 'x', 'REGULAR')",
            {"e": "alice.gaps@test"},
        )
        ids["userB"] = await _insert(
            "INSERT INTO users (email, name, password_hash, account_type) "
            "VALUES (:e, 'BobGaps', 'x', 'REGULAR')",
            {"e": "bob.gaps@test"},
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
            ("stages", "tournament_id", "tournament"),
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


# --- pure helper branches (no full tournament needed) ---


@pytest.mark.asyncio(loop_scope="session")
async def test_active_stage_is_last_returns_true_when_nothing_active(reinit_database) -> None:
    """_active_stage_is_last with no active stage -> True. (settlement.py line 45)"""
    # A tournament_id that has no stages at all: no active stage -> True.
    assert await _active_stage_is_last(-987654) is True


@pytest.mark.asyncio(loop_scope="session")
async def test_player_rating_status_empty_user_ids(reinit_database) -> None:
    """_player_rating_status short-circuits on an empty user list. (settlement.py line 64)"""
    assert await _player_rating_status(-1, []) == {}  # type: ignore[arg-type]


# --- validate_settlement_ready branches ---


@pytest.mark.asyncio(loop_scope="session")
async def test_settle_rejects_non_individual_tournament(
    reinit_database, rated_tournament: dict
) -> None:
    """A non-individual tournament can't settle. (settlement.py line 89)"""
    ids = rated_tournament
    await database.execute(
        "UPDATE tournaments SET is_individual = false WHERE id = :t", {"t": ids["tournament"]}
    )
    tournament = await sql_get_tournament(ids["tournament"])
    with pytest.raises(SettlementError, match="不参与积分"):
        await settle_tournament(tournament)


@pytest.mark.asyncio(loop_scope="session")
async def test_settle_rejects_when_active_stage_not_last(
    reinit_database, rated_tournament: dict
) -> None:
    """A later stage than the active one blocks settling. (settlement.py line 95)"""
    ids = rated_tournament
    # Add a second, later stage that is not active -> active stage is not last.
    await _insert(
        "INSERT INTO stages (name, tournament_id, is_active) VALUES ('S2', :t, false)",
        {"t": ids["tournament"]},
    )
    tournament = await sql_get_tournament(ids["tournament"])
    with pytest.raises(SettlementError, match="请先推进完所有阶段"):
        await settle_tournament(tournament)


@pytest.mark.asyncio(loop_scope="session")
async def test_settle_rejects_when_no_completed_matches(
    reinit_database, rated_tournament: dict
) -> None:
    """No formed/decided/both-bound match -> nothing to settle. (settlement.py line 118)"""
    ids = rated_tournament
    # Detach the match's inputs so no scored match is formed, but keep teams bound
    # and a tie-free state isn't the issue -- the scored list ends up empty.
    await database.execute("DELETE FROM matches WHERE id = :m", {"m": ids["match"]})
    tournament = await sql_get_tournament(ids["tournament"])
    with pytest.raises(SettlementError, match="还没有已完成的对阵可供结算"):
        await settle_tournament(tournament)


@pytest.mark.asyncio(loop_scope="session")
async def test_settle_rejects_when_participant_missing_initial_rating(
    reinit_database, rated_tournament: dict
) -> None:
    """A bound participant with no rating row blocks settling. (settlement.py line 125)"""
    ids = rated_tournament
    await database.execute(
        "DELETE FROM player_ratings WHERE category_id = :c AND user_id = :u",
        {"c": ids["category"], "u": ids["userB"]},
    )
    tournament = await sql_get_tournament(ids["tournament"])
    with pytest.raises(SettlementError, match="尚未设置初始积分"):
        await settle_tournament(tournament)


@pytest.mark.asyncio(loop_scope="session")
async def test_settle_winner_is_second_user_when_score1_lower(
    reinit_database, rated_tournament: dict
) -> None:
    """score1 < score2 -> winner is user_id2 (settlement.py line 175)."""
    ids = rated_tournament
    # Flip the score so input2 (Bob) wins.
    await database.execute(
        "UPDATE matches SET stage_item_input1_score = 1, stage_item_input2_score = 3 WHERE id = :m",
        {"m": ids["match"]},
    )
    tournament = await sql_get_tournament(ids["tournament"])
    result = await settle_tournament(tournament)
    assert result.status is SettlementStatus.SETTLED

    rows = {
        r["result"]: r["user_id"]
        for r in await database.fetch_all(
            "SELECT result, user_id FROM rating_events WHERE tournament_id = :t",
            {"t": ids["tournament"]},
        )
    }
    # Bob (input2) is recorded as the winner.
    assert rows["W"] == ids["userB"]
    assert rows["L"] == ids["userA"]


@pytest.mark.asyncio(loop_scope="session")
async def test_settle_skips_self_play_match(reinit_database, rated_tournament: dict) -> None:
    """A both-slots-same-user match is skipped (settlement.py lines 169-170)."""
    ids = rated_tournament
    # Point both slots of the match at the SAME input (Alice's team) so the formed
    # match resolves to user_id1 == user_id2 -> self-play.
    await database.execute(
        "UPDATE matches SET stage_item_input2_id = :i1 WHERE id = :m",
        {"i1": ids["inputA"], "m": ids["match"]},
    )

    tournament = await sql_get_tournament(ids["tournament"])
    # validate_settlement_ready passes (one bound participant, a decided match), and the
    # scoring loop skips the self-play match -> no rating events written.
    scored, _ = await validate_settlement_ready(tournament)
    assert scored, "expected a formed scored match"

    result = await settle_tournament(tournament)
    assert result.status is SettlementStatus.SETTLED
    events = await database.fetch_all(
        "SELECT 1 FROM rating_events WHERE tournament_id = :t", {"t": ids["tournament"]}
    )
    assert events == []


@pytest.mark.asyncio(loop_scope="session")
async def test_settle_race_recheck_inside_lock(reinit_database, rated_tournament: dict) -> None:
    """The in-lock re-check rejects a tournament settled between validate and lock.
    (settlement.py line 157)"""
    ids = rated_tournament
    tournament = await sql_get_tournament(ids["tournament"])
    # Stamp settled_seq AFTER fetching the (still-unsettled) Tournament object, so the
    # cheap pre-check at line 91 passes but the in-lock re-check at line 157 catches it.
    await database.execute(
        "UPDATE tournaments SET settled_seq = 99 WHERE id = :t", {"t": ids["tournament"]}
    )
    with pytest.raises(SettlementError, match="已经结算"):
        await settle_tournament(tournament)
