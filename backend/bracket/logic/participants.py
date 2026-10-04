"""Admitting an account into an individual tournament.

Auto-creates a same-named team + player and binds the account, all in one
transaction. The ``teams_x_users`` unique constraints turn a concurrent double
admit into a rollback (no orphan team left behind), per design §7.
"""

from __future__ import annotations

from heliclockter import datetime_utc

from bracket.database import database
from bracket.models.db.tournament import Tournament
from bracket.sql.teams import get_next_team_sort_order
from bracket.sql.users import get_user_by_id
from bracket.utils.id_types import TeamId, UserId


async def admit_user_to_tournament(tournament: Tournament, user_id: UserId) -> TeamId:
    """Create team+player and bind ``user_id``. Caller must ensure the tournament is
    individual and the user isn't already bound. Raises on unique violation (the
    transaction rolls back, leaving no orphan team)."""
    user = await get_user_by_id(user_id)
    if user is None:
        raise ValueError("User not found")

    now = datetime_utc.now()

    async with database.transaction():
        # Without an explicit sort_order the column default (0) would tie every
        # admitted participant, breaking the manual up/down ordering.
        team_id = await database.fetch_val(
            "INSERT INTO teams (name, tournament_id, created, sort_order) "
            "VALUES (:n, :t, :now, :so) RETURNING id",
            {
                "n": user.name,
                "t": tournament.id,
                "now": now,
                "so": await get_next_team_sort_order(tournament.id),
            },
        )
        player_id = await database.fetch_val(
            """
            INSERT INTO players
                (name, tournament_id, created, elo_score, wins, draws, losses, active)
            VALUES (:n, :t, :now, 1200, 0, 0, 0, true)
            RETURNING id
            """,
            {"n": user.name, "t": tournament.id, "now": now},
        )
        await database.execute(
            "INSERT INTO players_x_teams (player_id, team_id) VALUES (:p, :tm)",
            {"p": player_id, "tm": team_id},
        )
        # The binding insert is the concurrency gate: a second concurrent admit
        # hits UNIQUE(tournament_id, user_id) and rolls back the whole transaction.
        await database.execute(
            "INSERT INTO teams_x_users (team_id, user_id, tournament_id) VALUES (:tm, :u, :t)",
            {"tm": team_id, "u": user_id, "t": tournament.id},
        )

    return TeamId(team_id)
