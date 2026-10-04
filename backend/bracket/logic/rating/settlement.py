"""Batch-per-event settlement for the cross-tournament rating system.

A whole tournament settles as one batch, but each match is scored *sequentially*:
a player's rating updates immediately after each of their matches, and their next
match in the same tournament uses that updated rating — mirroring 开球网/ChinaTT's
own settlement ("每盘比赛的积分变化都要根据即时的积分来定，而不是整场比赛的赛前积分").
Matches are processed in a fixed schedule order (stage, round, match id — see
``get_definitive_matches_with_bindings``), not the real-world order they were
played in, so the result is deterministic and reproducible. Tournaments stack in
``settled_seq`` order (append-only) within a category.

All writes happen inside a single transaction with an advisory lock serialising
``settled_seq`` allocation, so two concurrent settlements can't collide.
"""

from __future__ import annotations

from heliclockter import datetime_utc

from bracket.database import database
from bracket.logic.rating.chinatt import compute_exchange
from bracket.models.db.rating import (
    ScoredMatch,
    SettlementResult,
    SettlementStatus,
)
from bracket.models.db.tournament import Tournament
from bracket.utils.i18n import tr
from bracket.utils.id_types import RatingCategoryId, UserId
from bracket.utils.logging import logger

# Constant key for the advisory lock that serialises settled_seq allocation.
_SETTLE_LOCK_KEY = 0x5A7714  # arbitrary, stable


class SettlementError(Exception):
    """Raised when a tournament isn't ready to settle. Message is user-facing."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


async def _active_stage_is_last(tournament_id: int) -> bool:
    active_id = await database.fetch_val(
        "SELECT id FROM stages WHERE tournament_id = :t AND is_active = TRUE LIMIT 1",
        {"t": tournament_id},
    )
    if active_id is None:
        return True  # nothing active to advance past
    later = await database.fetch_val(
        "SELECT EXISTS(SELECT 1 FROM stages WHERE tournament_id = :t AND id > :a)",
        {"t": tournament_id, "a": active_id},
    )
    return not later


async def _bound_user_ids(tournament_id: int) -> list[UserId]:
    rows = await database.fetch_all(
        "SELECT user_id FROM teams_x_users WHERE tournament_id = :t", {"t": tournament_id}
    )
    return [UserId(r["user_id"]) for r in rows]


async def _player_rating_status(
    category_id: RatingCategoryId, user_ids: list[UserId]
) -> dict[UserId, tuple[int, str]]:
    if not user_ids:
        return {}
    rows = await database.fetch_all(
        """
        SELECT user_id, current_rating, status FROM player_ratings
        WHERE category_id = :c AND user_id = ANY(:u)
        """,
        {"c": category_id, "u": user_ids},
    )
    return {UserId(r["user_id"]): (r["current_rating"], r["status"]) for r in rows}


async def validate_settlement_ready(
    tournament: Tournament,
) -> tuple[list[ScoredMatch], int]:
    """Validate that ``tournament`` can be settled.

    Returns ``(scored_matches, pending_review_count)`` or raises ``SettlementError``.
    """
    from bracket.sql.ratings import (
        get_definitive_matches_with_bindings,
        get_unbound_team_count,
        scored_matches_from_rows,
    )

    if not tournament.is_individual or tournament.rating_category_id is None:
        raise SettlementError(tr("本比赛不参与积分"))

    if tournament.settled_seq is not None:
        raise SettlementError(tr("本赛事已经结算过了"))

    if not await _active_stage_is_last(tournament.id):
        raise SettlementError(tr("请先推进完所有阶段再结算"))

    # Every team must be bound to an account.
    unbound = await get_unbound_team_count(tournament.id)
    if unbound > 0:
        raise SettlementError(tr("还有 {count} 支队伍未绑定账号，无法结算").format(count=unbound))

    rows = await get_definitive_matches_with_bindings(tournament.id)

    # Completeness gate: an already-formed, both-bound match left at a tie
    # (incl. 0-0) WITHOUT a forfeit marker means a match still hasn't been
    # recorded. A forfeit (0-0 + forfeit_input) IS a recorded result.
    for r in rows:
        if (
            r["user_id1"] is not None
            and r["user_id2"] is not None
            and r["score1"] == r["score2"]
            and r.get("forfeit_input") is None
        ):
            raise SettlementError(tr("仍有对阵没有录入结果"))

    scored = scored_matches_from_rows(rows)

    # Nothing to settle: with no formed, decided, both-bound match there is no
    # result to apply. Covers the empty tournament (no teams, no matches) and a
    # tournament whose matches are all still unplayed.
    if not scored:
        raise SettlementError(tr("还没有已完成的对阵可供结算"))

    # Every bound participant must have an initial rating on file.
    participants = await _bound_user_ids(tournament.id)
    statuses = await _player_rating_status(tournament.rating_category_id, participants)
    missing = [u for u in participants if u not in statuses]
    if missing:
        raise SettlementError(
            tr("有 {count} 名参赛者尚未设置初始积分，无法结算").format(count=len(missing))
        )

    pending_count = sum(1 for u in participants if statuses[u][1] == "PENDING")
    return scored, pending_count


async def apply_sequential_matches(
    category_id: RatingCategoryId,
    tournament_id: int,
    scored: list[ScoredMatch],
    entry_ratings: dict[UserId, int],
    created: datetime_utc,
) -> dict[UserId, int]:
    """Score ``scored`` (already in fixed schedule order) sequentially, writing one
    rating_events row per side per match, and return each player's final rating.

    Shared by the live settlement path and the historical backfill script, so both
    always apply the exact same algorithm.
    """
    current = dict(entry_ratings)

    for m in scored:
        if m.user_id1 == m.user_id2:
            logger.warning(f"Skipping self-play match {m.match_id} (user {m.user_id1})")
            continue

        if m.forfeit_input == 1:
            winner, loser = m.user_id2, m.user_id1
        elif m.forfeit_input == 2:
            winner, loser = m.user_id1, m.user_id2
        elif m.score1 > m.score2:
            winner, loser = m.user_id1, m.user_id2
        else:
            winner, loser = m.user_id2, m.user_id1

        w_before, l_before = current[winner], current[loser]
        gain, loss = compute_exchange(w_before, l_before)
        w_after, l_after = w_before + gain, l_before - loss

        await database.execute(
            """
            INSERT INTO rating_events
                (category_id, match_id, user_id, opponent_id, tournament_id,
                 rating_before, rating_after, delta, result, created)
            VALUES (:c, :m, :u, :o, :t, :rb, :ra, :d, 'W', :now)
            """,
            {
                "c": category_id,
                "m": m.match_id,
                "u": winner,
                "o": loser,
                "t": tournament_id,
                "rb": w_before,
                "ra": w_after,
                "d": gain,
                "now": created,
            },
        )
        await database.execute(
            """
            INSERT INTO rating_events
                (category_id, match_id, user_id, opponent_id, tournament_id,
                 rating_before, rating_after, delta, result, created)
            VALUES (:c, :m, :u, :o, :t, :rb, :ra, :d, 'L', :now)
            """,
            {
                "c": category_id,
                "m": m.match_id,
                "u": loser,
                "o": winner,
                "t": tournament_id,
                "rb": l_before,
                "ra": l_after,
                "d": -loss,
                "now": created,
            },
        )
        current[winner], current[loser] = w_after, l_after

    return current


async def settle_tournament(tournament: Tournament) -> SettlementResult:
    """Settle a tournament as one batch. Caller must hold owner/admin authorisation."""
    assert tournament.rating_category_id is not None
    category_id = tournament.rating_category_id

    scored, pending_count = await validate_settlement_ready(tournament)
    if pending_count > 0:
        return SettlementResult(
            status=SettlementStatus.PENDING_REVIEW,
            pending_review_count=pending_count,
            message="Awaiting admin review of initial ratings",
        )

    now = datetime_utc.now()

    async with database.transaction():
        # Serialise settled_seq allocation across concurrent settlements.
        await database.execute("SELECT pg_advisory_xact_lock(:k)", {"k": _SETTLE_LOCK_KEY})

        # Re-check not-yet-settled inside the lock (guards against a race).
        already = await database.fetch_val(
            "SELECT settled_seq FROM tournaments WHERE id = :t", {"t": tournament.id}
        )
        if already is not None:
            raise SettlementError(tr("本赛事已经结算过了"))

        seq = await database.fetch_val("SELECT COALESCE(MAX(settled_seq), 0) + 1 FROM tournaments")

        # Each player's rating going into this tournament.
        participants = await _bound_user_ids(tournament.id)
        statuses = await _player_rating_status(category_id, participants)
        entry_ratings = {u: statuses[u][0] for u in participants}

        final_ratings = await apply_sequential_matches(
            category_id, tournament.id, scored, entry_ratings, now
        )

        # Commit new current ratings (already fully up to date); derive
        # matches_played from the ledger.
        for u in participants:
            played = await database.fetch_val(
                "SELECT COUNT(*) FROM rating_events WHERE category_id = :c AND user_id = :u",
                {"c": category_id, "u": u},
            )
            await database.execute(
                """
                UPDATE player_ratings
                SET current_rating = :r, matches_played = :p, last_updated = :now
                WHERE category_id = :c AND user_id = :u
                """,
                {"r": final_ratings[u], "p": played, "now": now, "c": category_id, "u": u},
            )

        await database.execute(
            "UPDATE tournaments SET settled_seq = :s, settled_at = :now WHERE id = :t",
            {"s": seq, "now": now, "t": tournament.id},
        )

    return SettlementResult(
        status=SettlementStatus.SETTLED,
        settled_seq=seq,
        message="Settled",
    )
