"""Integration tests for participant admission, trusted managers and scorers."""

from collections.abc import AsyncIterator

import asyncpg  # type: ignore[import-untyped]
import pytest
import pytest_asyncio
from heliclockter import datetime_utc

from bracket.database import database
from bracket.logic.participants import admit_user_to_tournament
from bracket.sql.participants import (
    add_scorer,
    add_trusted_manager,
    get_scorers,
    get_trusted_managers,
    get_user_team_in_tournament,
    is_bound_in_tournament,
    is_trusted_manager,
    is_tournament_scorer,
    remove_scorer,
    remove_trusted_manager,
    tournament_has_matches,
)
from bracket.sql.tournaments import sql_get_tournament


async def _insert(query: str, values: dict) -> int:
    return await database.fetch_val(query + " RETURNING id", values)


@pytest_asyncio.fixture(loop_scope="session")
async def individual_tournament(reinit_database) -> AsyncIterator[dict]:
    now = datetime_utc.now()
    ids: dict = {}
    try:
        ids["club"] = await _insert("INSERT INTO clubs (name) VALUES ('C')", {})
        ids["tournament"] = await _insert(
            """
            INSERT INTO tournaments (name, start_time, club_id, dashboard_public, is_individual)
            VALUES ('T', :now, :club, true, true)
            """,
            {"now": now, "club": ids["club"]},
        )
        for who in ("A", "B"):
            ids[f"user{who}"] = await _insert(
                "INSERT INTO users (email, name, password_hash, account_type) "
                "VALUES (:e, :n, 'x', 'REGULAR')",
                {"e": f"{who}@test", "n": f"User {who}"},
            )
        yield ids
    finally:
        for table, col, key in [
            ("teams_x_users", "tournament_id", "tournament"),
            ("players_x_teams", "team_id", None),
            ("tournament_scorers", "tournament_id", "tournament"),
            ("players", "tournament_id", "tournament"),
            ("teams", "tournament_id", "tournament"),
            ("user_trusted_managers", "user_id", "userA"),
            ("tournaments", "id", "tournament"),
            ("users", "id", "userA"),
            ("users", "id", "userB"),
            ("clubs", "id", "club"),
        ]:
            if key is None:
                continue
            if key in ids:
                await database.execute(f"DELETE FROM {table} WHERE {col} = :v", {"v": ids[key]})


@pytest.mark.asyncio(loop_scope="session")
async def test_admit_creates_team_player_and_binding(
    reinit_database, individual_tournament: dict
) -> None:
    ids = individual_tournament
    tournament = await sql_get_tournament(ids["tournament"])
    team_id = await admit_user_to_tournament(tournament, ids["userA"])

    team = await database.fetch_one("SELECT name FROM teams WHERE id = :id", {"id": team_id})
    assert team["name"] == "User A"

    player_count = await database.fetch_val(
        "SELECT COUNT(*) FROM players_x_teams WHERE team_id = :tm", {"tm": team_id}
    )
    assert player_count == 1
    assert await is_bound_in_tournament(ids["tournament"], ids["userA"]) is True


@pytest.mark.asyncio(loop_scope="session")
async def test_admitted_teams_get_distinct_sort_order(
    reinit_database, individual_tournament: dict
) -> None:
    """Admitted participants used to fall back to the column default (0), tying every
    team and breaking the manual up/down ordering."""
    ids = individual_tournament
    tournament = await sql_get_tournament(ids["tournament"])
    await admit_user_to_tournament(tournament, ids["userA"])
    await admit_user_to_tournament(tournament, ids["userB"])

    sort_orders = [
        row["sort_order"]
        for row in await database.fetch_all(
            "SELECT sort_order FROM teams WHERE tournament_id = :t ORDER BY id",
            {"t": ids["tournament"]},
        )
    ]
    assert len(set(sort_orders)) == 2
    assert sort_orders[0] < sort_orders[1]


@pytest.mark.asyncio(loop_scope="session")
async def test_double_admit_leaves_no_orphan_team(
    reinit_database, individual_tournament: dict
) -> None:
    ids = individual_tournament
    tournament = await sql_get_tournament(ids["tournament"])
    await admit_user_to_tournament(tournament, ids["userA"])

    with pytest.raises(asyncpg.exceptions.UniqueViolationError):
        await admit_user_to_tournament(tournament, ids["userA"])

    # The failed second admit's team was rolled back: only one team exists.
    team_count = await database.fetch_val(
        "SELECT COUNT(*) FROM teams WHERE tournament_id = :t", {"t": ids["tournament"]}
    )
    assert team_count == 1


@pytest.mark.asyncio(loop_scope="session")
async def test_team_lookup_and_no_matches(reinit_database, individual_tournament: dict) -> None:
    ids = individual_tournament
    tournament = await sql_get_tournament(ids["tournament"])

    # Fresh tournament: play hasn't started, so join/leave are allowed.
    assert await tournament_has_matches(ids["tournament"]) is False

    team_id = await admit_user_to_tournament(tournament, ids["userA"])
    assert await get_user_team_in_tournament(ids["tournament"], ids["userA"]) == team_id
    # An account that never joined has no team.
    assert await get_user_team_in_tournament(ids["tournament"], ids["userB"]) is None


@pytest.mark.asyncio(loop_scope="session")
async def test_trusted_manager_roundtrip(reinit_database, individual_tournament: dict) -> None:
    ids = individual_tournament
    await add_trusted_manager(ids["userA"], ids["userB"])
    assert await is_trusted_manager(ids["userA"], ids["userB"]) is True
    managers = await get_trusted_managers(ids["userA"])
    assert [m.manager_id for m in managers] == [ids["userB"]]

    await remove_trusted_manager(ids["userA"], ids["userB"])
    assert await is_trusted_manager(ids["userA"], ids["userB"]) is False


@pytest.mark.asyncio(loop_scope="session")
async def test_scorer_roundtrip(reinit_database, individual_tournament: dict) -> None:
    ids = individual_tournament
    await add_scorer(ids["tournament"], ids["userB"])
    assert await is_tournament_scorer(ids["tournament"], ids["userB"]) is True
    scorers = await get_scorers(ids["tournament"])
    assert [s.user_id for s in scorers] == [ids["userB"]]

    await remove_scorer(ids["tournament"], ids["userB"])
    assert await is_tournament_scorer(ids["tournament"], ids["userB"]) is False
