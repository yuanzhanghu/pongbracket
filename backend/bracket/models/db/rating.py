from __future__ import annotations

from enum import auto

from heliclockter import datetime_utc
from pydantic import Field

from bracket.models.db.shared import BaseModelORM
from bracket.utils.i18n import SEEDED_RATING_CATEGORY_NAME, tr
from bracket.utils.id_types import (
    PlayerRatingId,
    RatingCategoryId,
    RatingEventId,
    TournamentId,
    UserId,
)
from bracket.utils.types import EnumAutoStr


class PlayerRatingStatus(EnumAutoStr):
    PENDING = auto()
    ACTIVE = auto()


class RatingEventResult(EnumAutoStr):
    W = auto()
    L = auto()


# --- Rating categories ---

# The seeded built-in category (加华积分). It anchors the whole cross-tournament
# rating system and must never be deleted, even by an admin.
PROTECTED_RATING_CATEGORY_KEY = "CanadaChinaTT"


def display_rating_category_name(key: str, name: str) -> str:
    """The name of a rating category as the client should see it, per request language.

    Only the built-in category still carrying its seeded Chinese name is translated. An
    admin may rename that category, and from then on their name is what everyone sees, in
    every language — an operator's choice is never overwritten. This is read-side only:
    the stored name, and every lookup, match and write, keep using the raw value.
    """
    if key == PROTECTED_RATING_CATEGORY_KEY and name == SEEDED_RATING_CATEGORY_NAME:
        return tr(name)
    return name


class RatingCategoryInsertable(BaseModelORM):
    key: str
    name: str
    algorithm: str = "chinatt"


class RatingCategory(RatingCategoryInsertable):
    id: RatingCategoryId
    created: datetime_utc


class RatingCategoryCreateBody(BaseModelORM):
    key: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1)
    algorithm: str = "chinatt"


class RatingCategoryUpdateBody(BaseModelORM):
    name: str = Field(..., min_length=1)
    algorithm: str = "chinatt"


# --- Player ratings ---


class PlayerRating(BaseModelORM):
    id: PlayerRatingId
    category_id: RatingCategoryId
    user_id: UserId
    initial_rating: int
    current_rating: int
    status: PlayerRatingStatus
    approved_by: UserId | None = None
    approved_at: datetime_utc | None = None
    matches_played: int = 0
    last_updated: datetime_utc


class SeedRatingBody(BaseModelORM):
    rating: int = Field(..., ge=0, le=4000)


class SettlementReviewPlayer(BaseModelORM):
    """One participant's PENDING seed inside a tournament awaiting settlement."""

    player_rating_id: PlayerRatingId
    user_id: UserId
    user_name: str
    initial_rating: int


class SettlementReviewItem(BaseModelORM):
    """A tournament whose owner requested settlement while seeds are still PENDING.
    The admin approves these seeds (optionally adjusted) and settles in one action."""

    tournament_id: TournamentId
    tournament_name: str
    category_id: RatingCategoryId
    category_name: str
    requested_at: datetime_utc
    players: list[SettlementReviewPlayer]


class RatingAdjustment(BaseModelORM):
    player_rating_id: PlayerRatingId
    initial_rating: int = Field(..., ge=0, le=4000)


class ApproveSettleBody(BaseModelORM):
    # Optional per-player adjusted seeds; omitted players keep the owner's value.
    adjustments: list[RatingAdjustment] = []


# --- Leaderboard ---


class LeaderboardEntry(BaseModelORM):
    user_id: UserId
    name: str
    current_rating: int
    matches_played: int


class AdminUserRatings(BaseModelORM):
    """One row of the admin user list: a user and their ACTIVE rating per category."""

    user_id: UserId
    name: str
    # category_id -> current rating; categories the user has no approved rating
    # in are simply absent.
    ratings: dict[RatingCategoryId, int] = {}


# --- Rating events (ledger) ---


class RatingEvent(BaseModelORM):
    id: RatingEventId
    category_id: RatingCategoryId
    match_id: int
    user_id: UserId
    opponent_id: UserId
    tournament_id: TournamentId
    rating_before: int
    rating_after: int
    delta: int
    result: RatingEventResult
    created: datetime_utc


class RatingEventWithNames(RatingEvent):
    opponent_name: str
    tournament_name: str


# --- My ratings (current user) ---


class MyRatingSummary(BaseModelORM):
    category_id: RatingCategoryId
    category_key: str
    category_name: str
    status: PlayerRatingStatus
    current_rating: int
    matches_played: int
    # Average of rating_after across the last 365 days of events; None if the
    # player has no events in that window (e.g. inactive this year).
    yearly_avg_rating: float | None = None
    # Highest rating ever reached, including the initial seed (a player can
    # peak at seeding time and only lose rating afterwards).
    peak_rating: int
    last_updated: datetime_utc


# --- Settlement ---


class SettlementStatus(EnumAutoStr):
    SETTLED = auto()
    PENDING_REVIEW = auto()


class SettlementResult(BaseModelORM):
    status: SettlementStatus
    settled_seq: int | None = None
    pending_review_count: int = 0
    # True once the owner has requested settlement and it is waiting in the admin
    # queue (seeds still PENDING). The owner should not press "申请积分结算" again.
    settlement_requested: bool = False
    message: str = ""


class ScoredMatch(BaseModelORM):
    """A resolved, already-formed match between two bound accounts."""

    match_id: int
    user_id1: UserId
    user_id2: UserId
    score1: int
    score2: int
    # 1 = input1 forfeited (input2 wins), 2 = input2 forfeited (input1 wins),
    # None = decided by score. A forfeit has 0-0 scores but is still a result.
    forfeit_input: int | None = None
