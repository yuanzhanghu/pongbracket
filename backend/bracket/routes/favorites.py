from fastapi import APIRouter, Depends, HTTPException
from starlette import status

from bracket.config import config
from bracket.models.db.user import UserPublic
from bracket.routes.auth import user_authenticated
from bracket.routes.models import SuccessResponse, TournamentsResponse
from bracket.sql.favorites import (
    add_favorite,
    get_followed_tournaments,
    remove_favorite,
)
from bracket.sql.participants import is_bound_in_tournament
from bracket.sql.tournaments import sql_get_tournament
from bracket.sql.users import get_user_access_to_tournament
from bracket.utils.i18n import tr
from bracket.utils.id_types import TournamentId

router = APIRouter(prefix=config.api_prefix)


@router.get("/me/tournaments", response_model=TournamentsResponse)
async def list_followed_tournaments(
    user: UserPublic = Depends(user_authenticated),
) -> TournamentsResponse:
    """Tournaments the user follows (favorited or participates in)."""
    return TournamentsResponse(data=await get_followed_tournaments(user.id))


@router.post("/me/favorites/{tournament_id}", response_model=SuccessResponse)
async def add_my_favorite(
    tournament_id: TournamentId,
    user: UserPublic = Depends(user_authenticated),
) -> SuccessResponse:
    # A user may only favorite a tournament they can actually view: a public
    # dashboard, one they organise (club member), or one they participate in.
    # This prevents bookmarking — and thereby probing — private tournaments.
    tournament = await sql_get_tournament(tournament_id)
    may_view = (
        tournament.dashboard_public
        or await get_user_access_to_tournament(tournament_id, user.id)
        or await is_bound_in_tournament(tournament_id, user.id)
    )
    if not may_view:
        raise HTTPException(status.HTTP_403_FORBIDDEN, tr("无法关注你无权查看的比赛"))
    await add_favorite(user.id, tournament_id)
    return SuccessResponse()


@router.delete("/me/favorites/{tournament_id}", response_model=SuccessResponse)
async def remove_my_favorite(
    tournament_id: TournamentId,
    user: UserPublic = Depends(user_authenticated),
) -> SuccessResponse:
    await remove_favorite(user.id, tournament_id)
    return SuccessResponse()
