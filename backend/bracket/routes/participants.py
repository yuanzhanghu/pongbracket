from fastapi import APIRouter, Depends, HTTPException
from heliclockter import datetime_utc
from starlette import status

from bracket.config import config
from bracket.logic.participants import admit_user_to_tournament
from bracket.models.db.participants import (
    AddableParticipantItem,
    JoinRequestBody,
    JoinStatusItem,
    ParticipantAddBody,
    ScorerAddBody,
    ScorerItem,
    TrustedManagerAddBody,
    TrustedManagerItem,
)
from bracket.models.db.tournament import Tournament
from bracket.models.db.user import UserPublic
from bracket.routes.auth import (
    user_authenticated,
    user_authenticated_for_tournament,
)
from bracket.routes.models import DataResponse, SuccessResponse, TournamentsResponse
from bracket.routes.util import disallow_archived_tournament
from bracket.sql.participants import (
    add_scorer,
    add_trusted_manager,
    get_addable_participants,
    get_club_owner_ids,
    get_joinable_tournaments,
    get_scorers,
    get_trusted_managers,
    get_user_team_in_tournament,
    is_bound_in_tournament,
    is_tournament_scorer,
    is_trusted_manager,
    remove_scorer,
    remove_trusted_manager,
    tournament_has_matches,
)
from bracket.sql.players import get_player_ids_in_team, sql_delete_player_if_orphaned
from bracket.sql.teams import sql_delete_team
from bracket.sql.tournaments import sql_get_tournament
from bracket.sql.users import get_user_access_to_tournament, get_user_by_login
from bracket.utils.errors import (
    ForeignKey,
    UniqueIndex,
    check_foreign_key_violation,
    check_unique_constraint_violation,
)
from bracket.utils.i18n import tr
from bracket.utils.id_types import TournamentId, UserId

router = APIRouter(prefix=config.api_prefix)


def _tournament_day_passed(tournament: Tournament) -> bool:
    """Whether the tournament's day is over (UTC day granularity): a tournament
    dated today still accepts signups; yesterday's and older do not."""
    today_start = datetime_utc.now().replace(hour=0, minute=0, second=0, microsecond=0)
    return tournament.start_time < today_start


class TrustedManagersResponse(DataResponse[list[TrustedManagerItem]]):
    pass


class ScorersResponse(DataResponse[list[ScorerItem]]):
    pass


class AddableParticipantsResponse(DataResponse[list[AddableParticipantItem]]):
    pass


class JoinStatusResponse(DataResponse[JoinStatusItem]):
    pass


async def _require_open_individual(tournament_id: TournamentId) -> Tournament:
    tournament = await sql_get_tournament(tournament_id)
    if not tournament.is_individual:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, tr("只有个人赛接受报名"))
    if tournament.settled_seq is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, tr("赛事已结算，参赛名单已锁定"))
    return tournament


# --- Join requests (applicant + owner) ---


@router.post("/tournaments/{tournament_id}/join-requests", response_model=SuccessResponse)
async def request_to_join(
    tournament_id: TournamentId,
    body: JoinRequestBody,
    user: UserPublic = Depends(user_authenticated),
) -> SuccessResponse:
    """A logged-in user joins an individual tournament directly — no creator
    approval, no rejection. Allowed only before play starts (no match generated)."""
    tournament = await sql_get_tournament(tournament_id)
    if not tournament.is_individual:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, tr("只有个人赛接受报名"))
    if tournament.settled_seq is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, tr("赛事已结算"))
    if _tournament_day_passed(tournament):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, tr("比赛日期已过，无法报名"))
    if await tournament_has_matches(tournament_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, tr("比赛已开始，无法加入"))
    if await is_bound_in_tournament(tournament_id, user.id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, tr("你已报名本比赛"))

    with check_unique_constraint_violation(
        {
            UniqueIndex.teams_x_users_tournament_id_user_id_key,
            UniqueIndex.teams_x_users_team_id_key,
        }
    ):
        await admit_user_to_tournament(tournament, user.id)

    # "信任创建者": authorise this club's owners to direct-add the user to their
    # future individual tournaments without re-asking.
    if body.trust_creator:
        for owner_id in await get_club_owner_ids(tournament.club_id):
            await add_trusted_manager(user.id, owner_id)

    return SuccessResponse()


@router.post("/tournaments/{tournament_id}/leave", response_model=SuccessResponse)
async def leave_tournament(
    tournament_id: TournamentId,
    user: UserPublic = Depends(user_authenticated),
) -> SuccessResponse:
    """A participant withdraws themselves — removing their single-person team and
    binding. Allowed only before play starts (no match generated) and never after
    settlement."""
    tournament = await sql_get_tournament(tournament_id)
    if not tournament.is_individual:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, tr("只有个人赛接受报名"))
    if tournament.settled_seq is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, tr("赛事已结算，无法退出"))
    if await tournament_has_matches(tournament_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, tr("比赛已开始，无法退出"))

    team_id = await get_user_team_in_tournament(tournament_id, user.id)
    if team_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, tr("你尚未参加此赛事"))

    player_ids = await get_player_ids_in_team(team_id)

    # If the team is already placed into a stage, deleting it would orphan that
    # input; surface a clean error instead of a 500.
    with check_foreign_key_violation({ForeignKey.stage_item_inputs_team_id_fkey}):
        await sql_delete_team(tournament_id, team_id)

    # The player record created on joining outlives the team otherwise.
    for player_id in player_ids:
        await sql_delete_player_if_orphaned(tournament_id, player_id)

    return SuccessResponse()


@router.get("/me/joinable-tournaments", response_model=TournamentsResponse)
async def list_joinable_tournaments(
    user: UserPublic = Depends(user_authenticated),
) -> TournamentsResponse:
    """Public individual tournaments the current user could join right now —
    the 可以参赛的比赛 tab on the home page."""
    return TournamentsResponse(data=await get_joinable_tournaments(user.id))


@router.get("/tournaments/{tournament_id}/my-join-status", response_model=JoinStatusResponse)
async def my_join_status(
    tournament_id: TournamentId,
    user: UserPublic = Depends(user_authenticated),
) -> JoinStatusResponse:
    """The current user's relationship to this tournament: whether they already
    participate (a bound team), can manage it, and can record scores. Used to pick
    the right 参赛 / 退出赛事 affordance."""
    tournament = await sql_get_tournament(tournament_id)
    can_manage = await get_user_access_to_tournament(tournament_id, user.id)
    is_scorer = await is_tournament_scorer(tournament_id, user.id)
    is_participant = await is_bound_in_tournament(tournament_id, user.id)

    # Join/leave is only open on an individual tournament that has not started
    # (no match generated yet) and is not settled. Joining additionally closes
    # once the tournament DAY has passed (same-day signups stay open); leaving
    # stays possible until the schedule is generated.
    has_matches = await tournament_has_matches(tournament_id)
    open_window = tournament.is_individual and tournament.settled_seq is None and not has_matches
    return JoinStatusResponse(
        data=JoinStatusItem(
            is_participant=is_participant,
            can_join=open_window and not _tournament_day_passed(tournament) and not is_participant,
            can_leave=open_window and is_participant,
            can_manage=can_manage,
            # Members and scorers may record/edit match scores.
            can_record=can_manage or is_scorer,
            has_matches=has_matches,
        )
    )


# --- Trusted-manager direct add ---


@router.get(
    "/tournaments/{tournament_id}/addable-participants",
    response_model=AddableParticipantsResponse,
)
async def list_addable_participants(
    tournament_id: TournamentId,
    user: UserPublic = Depends(user_authenticated_for_tournament),
) -> AddableParticipantsResponse:
    tournament = await _require_open_individual(tournament_id)
    return AddableParticipantsResponse(
        data=await get_addable_participants(
            tournament_id, tournament.club_id, include_all=user.is_admin
        )
    )


@router.post("/tournaments/{tournament_id}/participants", response_model=SuccessResponse)
async def add_participant(
    tournament_id: TournamentId,
    body: ParticipantAddBody,
    user: UserPublic = Depends(user_authenticated_for_tournament),
    __: Tournament = Depends(disallow_archived_tournament),
) -> SuccessResponse:
    tournament = await _require_open_individual(tournament_id)
    # A manager may always add THEMSELVES (a creator competing in their own
    # tournament). Site admins may add anyone; other managers need that
    # account's trust.
    if (
        body.user_id != user.id
        and not user.is_admin
        and not await is_trusted_manager(body.user_id, user.id)
    ):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            tr("该账号未授权你直接将其加入比赛"),
        )
    if await is_bound_in_tournament(tournament_id, body.user_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, tr("该账号已参加本比赛"))

    with check_unique_constraint_violation(
        {UniqueIndex.teams_x_users_tournament_id_user_id_key, UniqueIndex.teams_x_users_team_id_key}
    ):
        await admit_user_to_tournament(tournament, body.user_id)

    return SuccessResponse()


# --- My trusted managers ---


@router.get("/me/trusted-managers", response_model=TrustedManagersResponse)
async def list_trusted_managers(
    user: UserPublic = Depends(user_authenticated),
) -> TrustedManagersResponse:
    return TrustedManagersResponse(data=await get_trusted_managers(user.id))


@router.post("/me/trusted-managers", response_model=SuccessResponse)
async def add_my_trusted_manager(
    body: TrustedManagerAddBody,
    user: UserPublic = Depends(user_authenticated),
) -> SuccessResponse:
    manager = await get_user_by_login(body.manager_email)
    if manager is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, tr("没有找到该邮箱或名称对应的账号"))
    if manager.id == user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, tr("不能添加自己"))
    await add_trusted_manager(user.id, manager.id)
    return SuccessResponse()


@router.delete("/me/trusted-managers/{manager_id}", response_model=SuccessResponse)
async def remove_my_trusted_manager(
    manager_id: UserId,
    user: UserPublic = Depends(user_authenticated),
) -> SuccessResponse:
    await remove_trusted_manager(user.id, manager_id)
    return SuccessResponse()


# --- Scorers ---


@router.get("/tournaments/{tournament_id}/scorers", response_model=ScorersResponse)
async def list_scorers(
    tournament_id: TournamentId,
    _: UserPublic = Depends(user_authenticated_for_tournament),
) -> ScorersResponse:
    return ScorersResponse(data=await get_scorers(tournament_id))


@router.post("/tournaments/{tournament_id}/scorers", response_model=SuccessResponse)
async def add_tournament_scorer(
    tournament_id: TournamentId,
    body: ScorerAddBody,
    _: UserPublic = Depends(user_authenticated_for_tournament),
) -> SuccessResponse:
    scorer = await get_user_by_login(body.user_email)
    if scorer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, tr("没有找到该邮箱或名称对应的账号"))
    await add_scorer(tournament_id, scorer.id)
    return SuccessResponse()


@router.delete("/tournaments/{tournament_id}/scorers/{user_id}", response_model=SuccessResponse)
async def remove_tournament_scorer(
    tournament_id: TournamentId,
    user_id: UserId,
    _: UserPublic = Depends(user_authenticated_for_tournament),
) -> SuccessResponse:
    await remove_scorer(tournament_id, user_id)
    return SuccessResponse()
