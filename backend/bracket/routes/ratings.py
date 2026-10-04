from fastapi import APIRouter, Depends, HTTPException
from starlette import status

from bracket.config import config
from bracket.database import database
from bracket.logic.rating.settlement import (
    SettlementError,
    settle_tournament,
    validate_settlement_ready,
)
from bracket.models.db.rating import (
    PROTECTED_RATING_CATEGORY_KEY,
    ApproveSettleBody,
    LeaderboardEntry,
    MyRatingSummary,
    PlayerRating,
    RatingCategory,
    RatingCategoryCreateBody,
    RatingCategoryUpdateBody,
    RatingEventWithNames,
    SeedRatingBody,
    SettlementResult,
    SettlementReviewItem,
    SettlementStatus,
)
from bracket.models.db.team import Team
from bracket.models.db.tournament import Tournament
from bracket.models.db.user import UserPublic
from bracket.routes.auth import (
    user_authenticated,
    user_authenticated_admin,
    user_authenticated_for_tournament,
)
from bracket.routes.models import DataResponse, SuccessResponse
from bracket.routes.util import disallow_archived_tournament, team_dependency
from bracket.sql.ratings import (
    approve_player_rating,
    category_has_settled_tournaments,
    clear_settlement_requested,
    create_rating_category,
    delete_rating_category,
    get_leaderboard,
    get_pending_rating_ids_for_tournament,
    get_player_rating,
    get_player_ratings_for_user,
    get_rating_categories,
    get_rating_category,
    get_rating_events_for_user,
    get_settlement_review_queue,
    get_team_bound_user,
    mark_settlement_requested,
    update_rating_category,
    upsert_pending_player_rating,
)
from bracket.sql.tournaments import sql_get_tournament
from bracket.utils.errors import UniqueIndex, check_unique_constraint_violation
from bracket.utils.i18n import tr
from bracket.utils.id_types import RatingCategoryId, TournamentId

router = APIRouter(prefix=config.api_prefix)


class RatingCategoriesResponse(DataResponse[list[RatingCategory]]):
    pass


class RatingCategoryResponse(DataResponse[RatingCategory]):
    pass


class LeaderboardResponse(DataResponse[list[LeaderboardEntry]]):
    pass


class SettlementReviewsResponse(DataResponse[list[SettlementReviewItem]]):
    pass


class PlayerRatingResponse(DataResponse[PlayerRating | None]):
    pass


class SettlementResponse(DataResponse[SettlementResult]):
    pass


class MyRatingsResponse(DataResponse[list[MyRatingSummary]]):
    pass


class MyRatingEventsResponse(DataResponse[list[RatingEventWithNames]]):
    pass


# --- Rating categories (global) ---


@router.get("/rating-categories", response_model=RatingCategoriesResponse)
async def list_rating_categories(
    _: UserPublic = Depends(user_authenticated),
) -> RatingCategoriesResponse:
    return RatingCategoriesResponse(data=await get_rating_categories())


@router.post("/rating-categories", response_model=RatingCategoryResponse)
async def create_category(
    body: RatingCategoryCreateBody,
    _: UserPublic = Depends(user_authenticated_admin),
) -> RatingCategoryResponse:
    with check_unique_constraint_violation({UniqueIndex.rating_categories_key_key}):
        new_id = await create_rating_category(body.key, body.name, body.algorithm)
    category = await get_rating_category(new_id)
    assert category is not None
    return RatingCategoryResponse(data=category)


@router.put("/rating-categories/{category_id}", response_model=RatingCategoryResponse)
async def update_category(
    category_id: RatingCategoryId,
    body: RatingCategoryUpdateBody,
    _: UserPublic = Depends(user_authenticated_admin),
) -> RatingCategoryResponse:
    if await get_rating_category(category_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, tr("找不到该积分类别"))
    await update_rating_category(category_id, body.name, body.algorithm)
    category = await get_rating_category(category_id)
    assert category is not None
    return RatingCategoryResponse(data=category)


@router.delete("/rating-categories/{category_id}", response_model=SuccessResponse)
async def remove_category(
    category_id: RatingCategoryId,
    _: UserPublic = Depends(user_authenticated_admin),
) -> SuccessResponse:
    category = await get_rating_category(category_id)
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, tr("找不到该积分类别"))
    if category.key == PROTECTED_RATING_CATEGORY_KEY:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            tr("内置积分类别「{name}」不可删除").format(name=category.name),
        )
    if await category_has_settled_tournaments(category_id):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            tr("该积分类别下已有结算赛事，无法删除"),
        )
    # Without this guard a category still referenced by tournaments or player
    # ratings dies with a raw FK violation (500) instead of a clear message.
    in_use = await database.fetch_val(
        """
        SELECT EXISTS(SELECT 1 FROM tournaments WHERE rating_category_id = :c)
            OR EXISTS(SELECT 1 FROM player_ratings WHERE category_id = :c)
        """,
        {"c": category_id},
    )
    if in_use:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            tr("该积分类别仍被比赛或选手积分引用，无法删除"),
        )
    await delete_rating_category(category_id)
    return SuccessResponse()


@router.get("/rating-categories/{category_id}/leaderboard", response_model=LeaderboardResponse)
async def leaderboard(category_id: RatingCategoryId) -> LeaderboardResponse:
    # Public: only ACTIVE ratings are exposed (PENDING seeds are hidden).
    return LeaderboardResponse(data=await get_leaderboard(category_id))


# --- My ratings (current user) ---


@router.get("/me/ratings", response_model=MyRatingsResponse)
async def my_ratings(
    user: UserPublic = Depends(user_authenticated),
) -> MyRatingsResponse:
    return MyRatingsResponse(data=await get_player_ratings_for_user(user.id))


@router.get("/me/ratings/{category_id}/events", response_model=MyRatingEventsResponse)
async def my_rating_events(
    category_id: RatingCategoryId,
    user: UserPublic = Depends(user_authenticated),
) -> MyRatingEventsResponse:
    return MyRatingEventsResponse(data=await get_rating_events_for_user(category_id, user.id))


# --- Admin review queue ---


@router.get("/admin/settlement-reviews", response_model=SettlementReviewsResponse)
async def settlement_reviews(
    _: UserPublic = Depends(user_authenticated_admin),
) -> SettlementReviewsResponse:
    return SettlementReviewsResponse(data=await get_settlement_review_queue())


@router.post(
    "/admin/settlements/{tournament_id}/approve-and-settle", response_model=SettlementResponse
)
async def approve_and_settle(
    tournament_id: TournamentId,
    body: ApproveSettleBody,
    admin: UserPublic = Depends(user_authenticated_admin),
) -> SettlementResponse:
    """One admin action: approve every PENDING seed of this tournament's participants
    (applying any per-player adjustment) and settle — atomically. The adjusted seed
    becomes the player's frozen entry rating, so the settlement reflects it."""
    tournament = await sql_get_tournament(tournament_id)
    category_id = await _require_rated_individual(tournament)
    adjustments = {a.player_rating_id: a.initial_rating for a in body.adjustments}

    try:
        async with database.transaction():
            pending_ids = await get_pending_rating_ids_for_tournament(tournament_id, category_id)
            for player_rating_id in pending_ids:
                await approve_player_rating(
                    player_rating_id, admin.id, adjustments.get(player_rating_id)
                )
            result = await settle_tournament(tournament)
            if result.status is not SettlementStatus.SETTLED:
                # Should not happen: seeds were just approved. Roll back to be safe.
                raise SettlementError(result.message or tr("结算未能完成"))
            await clear_settlement_requested(tournament_id)
    except SettlementError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, exc.message) from exc

    return SettlementResponse(data=result)


# --- Owner: rating settings, pre-seeding, settlement ---


async def _require_rated_individual(tournament: Tournament) -> RatingCategoryId:
    if not tournament.is_individual or tournament.rating_category_id is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            tr("本比赛不参与积分"),
        )
    return tournament.rating_category_id


@router.put(
    "/tournaments/{tournament_id}/teams/{team_id}/seed-rating",
    response_model=PlayerRatingResponse,
)
async def seed_team_rating(
    tournament_id: TournamentId,
    body: SeedRatingBody,
    _: UserPublic = Depends(user_authenticated_for_tournament),
    __: Tournament = Depends(disallow_archived_tournament),
    team: Team = Depends(team_dependency),
) -> PlayerRatingResponse:
    tournament = await sql_get_tournament(tournament_id)
    category_id = await _require_rated_individual(tournament)

    if tournament.settled_seq is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, tr("已结算的赛事不能再修改初始积分"))

    user_id = await get_team_bound_user(team.id)
    if user_id is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            tr("该队伍尚未绑定账号"),
        )

    existing = await get_player_rating(category_id, user_id)
    if existing is not None and existing.status.value == "ACTIVE":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            tr("该账号已有生效积分，不能再设置初始积分"),
        )

    await upsert_pending_player_rating(category_id, user_id, body.rating)
    return PlayerRatingResponse(data=await get_player_rating(category_id, user_id))


@router.post("/tournaments/{tournament_id}/settlement-request", response_model=SettlementResponse)
async def settlement_request(
    tournament_id: TournamentId,
    _: UserPublic = Depends(user_authenticated_for_tournament),
) -> SettlementResponse:
    tournament = await sql_get_tournament(tournament_id)
    try:
        # When no newcomer ratings are pending review, the owner settles directly.
        result = await settle_tournament(tournament)
    except SettlementError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, exc.message) from exc

    # Seeds still pending: park the tournament in the admin queue and tell the owner
    # it's submitted — they never press this again. The admin approves & settles.
    if result.status is SettlementStatus.PENDING_REVIEW:
        await mark_settlement_requested(tournament_id)
        result.settlement_requested = True
        result.message = tr("已提交，待管理员审核初始分并完成结算")
    return SettlementResponse(data=result)


@router.post("/tournaments/{tournament_id}/settle", response_model=SettlementResponse)
async def settle(
    tournament_id: TournamentId,
    _: UserPublic = Depends(user_authenticated_admin),
) -> SettlementResponse:
    tournament = await sql_get_tournament(tournament_id)
    try:
        result = await settle_tournament(tournament)
    except SettlementError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, exc.message) from exc

    if result.status is SettlementStatus.PENDING_REVIEW:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            tr("初始积分仍在审核中，请先完成审核"),
        )
    return SettlementResponse(data=result)


@router.get("/tournaments/{tournament_id}/settlement-status", response_model=SettlementResponse)
async def settlement_status(
    tournament_id: TournamentId,
    _: UserPublic = Depends(user_authenticated_for_tournament),
) -> SettlementResponse:
    tournament = await sql_get_tournament(tournament_id)
    if tournament.settled_seq is not None:
        return SettlementResponse(
            data=SettlementResult(
                status=SettlementStatus.SETTLED,
                settled_seq=tournament.settled_seq,
                message="Settled",
            )
        )
    try:
        _scored, pending = await validate_settlement_ready(tournament)
    except SettlementError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, exc.message) from exc

    requested = tournament.settlement_requested_at is not None
    if pending == 0:
        message = tr("可以结算")
    elif requested:
        message = tr("已提交，待管理员审核初始分并完成结算")
    else:
        message = tr("有 {count} 名选手的初始分待管理员审核").format(count=pending)
    return SettlementResponse(
        data=SettlementResult(
            status=SettlementStatus.PENDING_REVIEW if pending else SettlementStatus.SETTLED,
            pending_review_count=pending,
            settlement_requested=requested,
            message=message,
        )
    )
