from typing import Any

from heliclockter import datetime_utc

from bracket.database import database
from bracket.models.db.rating import (
    LeaderboardEntry,
    MyRatingSummary,
    PlayerRating,
    RatingCategory,
    RatingEventWithNames,
    ScoredMatch,
    SettlementReviewItem,
    SettlementReviewPlayer,
    display_rating_category_name,
)
from bracket.utils.id_types import (
    PlayerRatingId,
    RatingCategoryId,
    TournamentId,
    UserId,
)

# --- Rating categories ---


def _category_from_row(row: Any) -> RatingCategory:
    """Read a category row, showing the built-in one's seeded name in the request's
    language (see `display_rating_category_name`). `key` is left untouched, so callers
    keep matching on it."""
    category = RatingCategory.model_validate(row)
    category.name = display_rating_category_name(category.key, category.name)
    return category


async def get_rating_categories() -> list[RatingCategory]:
    result = await database.fetch_all("SELECT * FROM rating_categories ORDER BY id")
    return [_category_from_row(r) for r in result]


async def get_rating_category(category_id: RatingCategoryId) -> RatingCategory | None:
    result = await database.fetch_one(
        "SELECT * FROM rating_categories WHERE id = :id", {"id": category_id}
    )
    return _category_from_row(result) if result is not None else None


async def create_rating_category(key: str, name: str, algorithm: str) -> RatingCategoryId:
    new_id = await database.fetch_val(
        """
        INSERT INTO rating_categories (key, name, algorithm)
        VALUES (:key, :name, :algorithm)
        RETURNING id
        """,
        {"key": key, "name": name, "algorithm": algorithm},
    )
    return RatingCategoryId(new_id)


async def update_rating_category(category_id: RatingCategoryId, name: str, algorithm: str) -> None:
    await database.execute(
        "UPDATE rating_categories SET name = :name, algorithm = :algorithm WHERE id = :id",
        {"id": category_id, "name": name, "algorithm": algorithm},
    )


async def delete_rating_category(category_id: RatingCategoryId) -> None:
    await database.execute("DELETE FROM rating_categories WHERE id = :id", {"id": category_id})


async def category_has_settled_tournaments(category_id: RatingCategoryId) -> bool:
    count = await database.fetch_val(
        """
        SELECT COUNT(*) FROM tournaments
        WHERE rating_category_id = :id AND settled_seq IS NOT NULL
        """,
        {"id": category_id},
    )
    return count > 0


# --- Player ratings ---


async def get_player_rating(category_id: RatingCategoryId, user_id: UserId) -> PlayerRating | None:
    result = await database.fetch_one(
        "SELECT * FROM player_ratings WHERE category_id = :c AND user_id = :u",
        {"c": category_id, "u": user_id},
    )
    return PlayerRating.model_validate(result) if result is not None else None


async def upsert_pending_player_rating(
    category_id: RatingCategoryId, user_id: UserId, rating: int
) -> None:
    """Create or update a PENDING initial rating (used by owner pre-seeding)."""
    await database.execute(
        """
        INSERT INTO player_ratings
            (category_id, user_id, initial_rating, current_rating, status, last_updated)
        VALUES (:c, :u, :r, :r, 'PENDING', :now)
        ON CONFLICT (category_id, user_id) DO UPDATE
        SET initial_rating = :r, current_rating = :r, last_updated = :now
        WHERE player_ratings.status = 'PENDING'
        """,
        {"c": category_id, "u": user_id, "r": rating, "now": datetime_utc.now()},
    )


async def mark_settlement_requested(tournament_id: TournamentId) -> None:
    """Record that the owner requested settlement (seeds still PENDING). Idempotent:
    keeps the first request time so the queue order is stable."""
    await database.execute(
        """
        UPDATE tournaments
        SET settlement_requested_at = COALESCE(settlement_requested_at, :now)
        WHERE id = :t AND settled_seq IS NULL
        """,
        {"t": tournament_id, "now": datetime_utc.now()},
    )


async def clear_settlement_requested(tournament_id: TournamentId) -> None:
    await database.execute(
        "UPDATE tournaments SET settlement_requested_at = NULL WHERE id = :t",
        {"t": tournament_id},
    )


async def count_unrated_participants(
    tournament_id: TournamentId, category_id: RatingCategoryId
) -> int:
    """How many bound participants have NO rating (neither a PENDING initial nor an
    ACTIVE official one) in this category. Used to block starting the tournament."""
    return await database.fetch_val(
        """
        SELECT COUNT(*)
        FROM teams_x_users tu
        WHERE tu.tournament_id = :t
          AND NOT EXISTS (
              SELECT 1 FROM player_ratings pr
              WHERE pr.user_id = tu.user_id AND pr.category_id = :c
          )
        """,
        {"t": tournament_id, "c": category_id},
    )


async def get_pending_rating_ids_for_tournament(
    tournament_id: TournamentId, category_id: RatingCategoryId
) -> list[PlayerRatingId]:
    """PENDING seed rows of this tournament's bound participants, in this category."""
    rows = await database.fetch_all(
        """
        SELECT pr.id
        FROM player_ratings pr
        JOIN teams_x_users tu ON tu.user_id = pr.user_id AND tu.tournament_id = :t
        WHERE pr.category_id = :c AND pr.status = 'PENDING'
        """,
        {"t": tournament_id, "c": category_id},
    )
    return [PlayerRatingId(r["id"]) for r in rows]


async def get_settlement_review_queue() -> list[SettlementReviewItem]:
    """Tournaments whose owner requested settlement and that still have PENDING seeds.
    Each carries the participants whose seeds await approval."""
    tournaments = await database.fetch_all(
        """
        SELECT t.id AS tournament_id, t.name AS tournament_name,
               t.rating_category_id AS category_id, rc.key AS category_key,
               rc.name AS category_name,
               t.settlement_requested_at AS requested_at
        FROM tournaments t
        JOIN rating_categories rc ON rc.id = t.rating_category_id
        WHERE t.settlement_requested_at IS NOT NULL AND t.settled_seq IS NULL
        ORDER BY t.settlement_requested_at
        """
    )
    items: list[SettlementReviewItem] = []
    for t in tournaments:
        players = await database.fetch_all(
            """
            SELECT pr.id AS player_rating_id, pr.user_id,
                   u.name AS user_name, pr.initial_rating
            FROM player_ratings pr
            JOIN teams_x_users tu ON tu.user_id = pr.user_id AND tu.tournament_id = :t
            JOIN users u ON u.id = pr.user_id
            WHERE pr.category_id = :c AND pr.status = 'PENDING'
            ORDER BY u.name
            """,
            {"t": t["tournament_id"], "c": t["category_id"]},
        )
        items.append(
            SettlementReviewItem(
                tournament_id=t["tournament_id"],
                tournament_name=t["tournament_name"],
                category_id=t["category_id"],
                category_name=display_rating_category_name(t["category_key"], t["category_name"]),
                requested_at=t["requested_at"],
                players=[SettlementReviewPlayer.model_validate(p) for p in players],
            )
        )
    return items


async def approve_player_rating(
    player_rating_id: PlayerRatingId, admin_id: UserId, initial_rating: int | None
) -> None:
    if initial_rating is not None:
        await database.execute(
            """
            UPDATE player_ratings
            SET status = 'ACTIVE', approved_by = :a, approved_at = :now,
                initial_rating = :r, current_rating = :r, last_updated = :now
            WHERE id = :id AND status = 'PENDING'
            """,
            {"id": player_rating_id, "a": admin_id, "now": datetime_utc.now(), "r": initial_rating},
        )
    else:
        await database.execute(
            """
            UPDATE player_ratings
            SET status = 'ACTIVE', approved_by = :a, approved_at = :now, last_updated = :now
            WHERE id = :id AND status = 'PENDING'
            """,
            {"id": player_rating_id, "a": admin_id, "now": datetime_utc.now()},
        )


# --- Leaderboard ---


async def get_leaderboard(category_id: RatingCategoryId) -> list[LeaderboardEntry]:
    # Public: only ACTIVE (approved) ratings — never leak unreviewed seeds.
    result = await database.fetch_all(
        """
        SELECT pr.user_id, u.name, pr.current_rating, pr.matches_played
        FROM player_ratings pr
        JOIN users u ON u.id = pr.user_id
        WHERE pr.category_id = :c AND pr.status = 'ACTIVE'
        ORDER BY pr.current_rating DESC, pr.matches_played DESC, u.name ASC
        """,
        {"c": category_id},
    )
    return [LeaderboardEntry.model_validate(r) for r in result]


# --- Settlement helpers ---


async def get_definitive_matches_with_bindings(
    tournament_id: TournamentId,
) -> list[dict]:
    """All already-formed (both inputs are Final teams) matches in non-draft rounds,
    with each side's bound user (NULL when a team isn't linked to an account).

    Ordered by (stage, round, match id) — a fixed, deterministic schedule order
    used to settle matches sequentially (see settlement.py), independent of the
    real-world order matches were actually played in.
    """
    result = await database.fetch_all(
        """
        SELECT m.id AS match_id,
               m.stage_item_input1_score AS score1,
               m.stage_item_input2_score AS score2,
               m.forfeit_input AS forfeit_input,
               i1.team_id AS team_id1, i2.team_id AS team_id2,
               tu1.user_id AS user_id1, tu2.user_id AS user_id2
        FROM matches m
        JOIN rounds r ON m.round_id = r.id
        JOIN stage_items si ON r.stage_item_id = si.id
        JOIN stages s ON si.stage_id = s.id
        JOIN stage_item_inputs i1 ON m.stage_item_input1_id = i1.id
        JOIN stage_item_inputs i2 ON m.stage_item_input2_id = i2.id
        LEFT JOIN teams_x_users tu1 ON tu1.team_id = i1.team_id
        LEFT JOIN teams_x_users tu2 ON tu2.team_id = i2.team_id
        WHERE s.tournament_id = :t
          AND r.is_draft = FALSE
          AND i1.team_id IS NOT NULL
          AND i2.team_id IS NOT NULL
        ORDER BY s.id, r.id, m.id
        """,
        {"t": tournament_id},
    )
    return [dict(r) for r in result]


def scored_matches_from_rows(rows: list[dict]) -> list[ScoredMatch]:
    """Filter resolved rows to decided, both-bound matches (the ones that score).

    A match scores when it is decided by score (score1 != score2) OR by forfeit
    (forfeit_input is not None; scores are 0-0). An unplayed 0-0 match with no
    forfeit does NOT score.
    """
    out: list[ScoredMatch] = []
    for r in rows:
        if r["user_id1"] is None or r["user_id2"] is None:
            continue
        forfeit_input = r.get("forfeit_input")
        if r["score1"] == r["score2"] and forfeit_input is None:
            continue
        out.append(
            ScoredMatch(
                match_id=r["match_id"],
                user_id1=r["user_id1"],
                user_id2=r["user_id2"],
                score1=r["score1"],
                score2=r["score2"],
                forfeit_input=forfeit_input,
            )
        )
    return out


async def get_unbound_team_count(tournament_id: TournamentId) -> int:
    return await database.fetch_val(
        """
        SELECT COUNT(*) FROM teams t
        WHERE t.tournament_id = :t
          AND NOT EXISTS (SELECT 1 FROM teams_x_users tu WHERE tu.team_id = t.id)
        """,
        {"t": tournament_id},
    )


async def get_team_bound_user(team_id: int) -> UserId | None:
    result = await database.fetch_val(
        "SELECT user_id FROM teams_x_users WHERE team_id = :t", {"t": team_id}
    )
    return UserId(result) if result is not None else None


# --- My ratings (current user) ---


async def get_player_ratings_for_user(user_id: UserId) -> list[MyRatingSummary]:
    result = await database.fetch_all(
        """
        SELECT pr.category_id, rc.key AS category_key, rc.name AS category_name,
               pr.status, pr.current_rating, pr.matches_played, pr.last_updated,
               yearly.avg_rating AS yearly_avg_rating,
               GREATEST(pr.initial_rating, COALESCE(peak.max_rating, pr.initial_rating))
                   AS peak_rating
        FROM player_ratings pr
        JOIN rating_categories rc ON rc.id = pr.category_id
        LEFT JOIN LATERAL (
            SELECT AVG(re.rating_after) AS avg_rating
            FROM rating_events re
            WHERE re.category_id = pr.category_id AND re.user_id = pr.user_id
              AND re.created >= now() - interval '365 days'
        ) yearly ON TRUE
        LEFT JOIN LATERAL (
            SELECT MAX(re.rating_after) AS max_rating
            FROM rating_events re
            WHERE re.category_id = pr.category_id AND re.user_id = pr.user_id
        ) peak ON TRUE
        WHERE pr.user_id = :u
        ORDER BY rc.name
        """,
        {"u": user_id},
    )
    summaries = [MyRatingSummary.model_validate(r) for r in result]
    for summary in summaries:
        summary.category_name = display_rating_category_name(
            summary.category_key, summary.category_name
        )
    return summaries


async def get_rating_events_for_user(
    category_id: RatingCategoryId, user_id: UserId
) -> list[RatingEventWithNames]:
    result = await database.fetch_all(
        """
        SELECT re.*, ou.name AS opponent_name, t.name AS tournament_name
        FROM rating_events re
        JOIN users ou ON ou.id = re.opponent_id
        JOIN tournaments t ON t.id = re.tournament_id
        WHERE re.category_id = :c AND re.user_id = :u
        ORDER BY re.created ASC, re.id ASC
        """,
        {"c": category_id, "u": user_id},
    )
    return [RatingEventWithNames.model_validate(r) for r in result]
