from heliclockter import datetime_utc

from bracket.database import database
from bracket.models.db.participants import (
    AddableParticipantItem,
    ScorerItem,
    TrustedManagerItem,
)
from bracket.models.db.tournament import Tournament
from bracket.utils.id_types import (
    ClubId,
    TeamId,
    TournamentId,
    UserId,
)

# --- Membership ---


async def is_bound_in_tournament(tournament_id: TournamentId, user_id: UserId) -> bool:
    found = await database.fetch_val(
        "SELECT EXISTS(SELECT 1 FROM teams_x_users WHERE tournament_id = :t AND user_id = :u)",
        {"t": tournament_id, "u": user_id},
    )
    return bool(found)


async def tournament_has_matches(tournament_id: TournamentId) -> bool:
    """Whether play has started: any match row exists for this tournament. Gates
    self-service join/leave — both are only allowed before the schedule is built."""
    found = await database.fetch_val(
        """
        SELECT EXISTS(
            SELECT 1 FROM matches m
            JOIN rounds r ON m.round_id = r.id
            JOIN stage_items si ON r.stage_item_id = si.id
            JOIN stages s ON si.stage_id = s.id
            WHERE s.tournament_id = :t
        )
        """,
        {"t": tournament_id},
    )
    return bool(found)


async def sync_user_team_names(user_id: UserId, new_name: str) -> None:
    """Individual-tournament teams are created with the participant's name at
    join time; keep them in sync when the account is renamed. Settled
    tournaments keep their historical names."""
    await database.execute(
        """
        UPDATE teams te
        SET name = :name
        FROM teams_x_users txu, tournaments t
        WHERE txu.team_id = te.id
          AND txu.user_id = :user_id
          AND t.id = te.tournament_id
          AND t.settled_seq IS NULL
        """,
        {"user_id": user_id, "name": new_name},
    )


async def get_joinable_tournaments(user_id: UserId) -> list[Tournament]:
    """Public individual tournaments whose join window is open for this user:
    not settled, not archived, play hasn't started (no match generated), the
    tournament day hasn't passed (same-day still counts), and the user doesn't
    already participate. Mirrors the can_join rule of my-join-status, but
    across all public tournaments."""
    rows = await database.fetch_all(
        """
        SELECT t.*
        FROM tournaments t
        WHERE t.dashboard_public IS TRUE
          AND t.is_individual IS TRUE
          AND t.settled_seq IS NULL
          AND t.status = 'OPEN'
          AND t.start_time >= date_trunc('day', NOW())
          AND NOT EXISTS (
              SELECT 1 FROM teams_x_users txu
              WHERE txu.tournament_id = t.id AND txu.user_id = :u
          )
          AND NOT EXISTS (
              SELECT 1 FROM matches m
              JOIN rounds r ON m.round_id = r.id
              JOIN stage_items si ON r.stage_item_id = si.id
              JOIN stages s ON si.stage_id = s.id
              WHERE s.tournament_id = t.id
          )
        ORDER BY t.start_time DESC
        """,
        {"u": user_id},
    )
    return [Tournament.model_validate(r) for r in rows]


async def get_user_team_in_tournament(
    tournament_id: TournamentId, user_id: UserId
) -> TeamId | None:
    val = await database.fetch_val(
        "SELECT team_id FROM teams_x_users WHERE tournament_id = :t AND user_id = :u",
        {"t": tournament_id, "u": user_id},
    )
    return TeamId(val) if val is not None else None


async def get_club_owner_ids(club_id: ClubId) -> list[UserId]:
    rows = await database.fetch_all(
        "SELECT user_id FROM users_x_clubs WHERE club_id = :c AND relation = 'OWNER'",
        {"c": club_id},
    )
    return [UserId(r["user_id"]) for r in rows]


# --- Trusted managers ---


async def add_trusted_manager(user_id: UserId, manager_id: UserId) -> None:
    await database.execute(
        """
        INSERT INTO user_trusted_managers (user_id, manager_id, created)
        VALUES (:u, :m, :now)
        ON CONFLICT (user_id, manager_id) DO NOTHING
        """,
        {"u": user_id, "m": manager_id, "now": datetime_utc.now()},
    )


async def remove_trusted_manager(user_id: UserId, manager_id: UserId) -> None:
    await database.execute(
        "DELETE FROM user_trusted_managers WHERE user_id = :u AND manager_id = :m",
        {"u": user_id, "m": manager_id},
    )


async def get_trusted_managers(user_id: UserId) -> list[TrustedManagerItem]:
    rows = await database.fetch_all(
        """
        SELECT tm.manager_id, u.name
        FROM user_trusted_managers tm
        JOIN users u ON u.id = tm.manager_id
        WHERE tm.user_id = :u
        ORDER BY u.name
        """,
        {"u": user_id},
    )
    return [TrustedManagerItem.model_validate(r) for r in rows]


async def get_addable_participants(
    tournament_id: TournamentId, club_id: ClubId, include_all: bool = False
) -> list[AddableParticipantItem]:
    """Accounts the owner may add directly: the club's own owner(s) — so a
    creator can enter themselves into their own individual tournament — plus
    users who trust a club owner of this tournament (so direct-add is
    pre-authorised). Already-bound accounts are excluded.

    With include_all (site admins), every non-demo account is a candidate —
    admins may add anyone without per-user trust.

    This is what the owner's hosted-account picker lists — there is no free-text
    name entry on individual tournaments.
    """
    if include_all:
        candidates_sql = """
            SELECT id AS uid
            FROM users
            WHERE account_type != 'DEMO'
        """
    else:
        candidates_sql = """
            -- Users who trust an owner of this club (pre-authorised direct-add).
            SELECT tm.user_id AS uid
            FROM user_trusted_managers tm
            JOIN users_x_clubs uc
                ON uc.user_id = tm.manager_id AND uc.club_id = :c AND uc.relation = 'OWNER'
            UNION
            -- The club's own owner(s): a creator can always add themselves.
            SELECT uc2.user_id AS uid
            FROM users_x_clubs uc2
            WHERE uc2.club_id = :c AND uc2.relation = 'OWNER'
        """
    rows = await database.fetch_all(
        f"""
        SELECT DISTINCT u.id AS user_id, u.name
        FROM ({candidates_sql}) cand
        JOIN users u ON u.id = cand.uid
        WHERE NOT EXISTS (
            SELECT 1 FROM teams_x_users tu
            WHERE tu.tournament_id = :t AND tu.user_id = cand.uid
        )
        ORDER BY u.name
        """,
        {"t": tournament_id} if include_all else {"c": club_id, "t": tournament_id},
    )
    return [AddableParticipantItem.model_validate(r) for r in rows]


async def is_trusted_manager(user_id: UserId, manager_id: UserId) -> bool:
    found = await database.fetch_val(
        "SELECT EXISTS(SELECT 1 FROM user_trusted_managers WHERE user_id = :u AND manager_id = :m)",
        {"u": user_id, "m": manager_id},
    )
    return bool(found)


# --- Scorers ---


async def add_scorer(tournament_id: TournamentId, user_id: UserId) -> None:
    await database.execute(
        """
        INSERT INTO tournament_scorers (tournament_id, user_id) VALUES (:t, :u)
        ON CONFLICT (tournament_id, user_id) DO NOTHING
        """,
        {"t": tournament_id, "u": user_id},
    )


async def remove_scorer(tournament_id: TournamentId, user_id: UserId) -> None:
    await database.execute(
        "DELETE FROM tournament_scorers WHERE tournament_id = :t AND user_id = :u",
        {"t": tournament_id, "u": user_id},
    )


async def get_scorers(tournament_id: TournamentId) -> list[ScorerItem]:
    rows = await database.fetch_all(
        """
        SELECT ts.user_id, u.name
        FROM tournament_scorers ts
        JOIN users u ON u.id = ts.user_id
        WHERE ts.tournament_id = :t
        ORDER BY u.name
        """,
        {"t": tournament_id},
    )
    return [ScorerItem.model_validate(r) for r in rows]


async def is_tournament_scorer(tournament_id: TournamentId, user_id: UserId) -> bool:
    found = await database.fetch_val(
        "SELECT EXISTS(SELECT 1 FROM tournament_scorers WHERE tournament_id = :t AND user_id = :u)",
        {"t": tournament_id, "u": user_id},
    )
    return bool(found)
