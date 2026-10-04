from fastapi import APIRouter, Depends, HTTPException, Request
from heliclockter import datetime_utc
from pydantic import BaseModel
from starlette import status

from bracket.config import config
from bracket.logic.ranking.calculation import determine_team_ranking_for_stage_item
from bracket.models.db.stage_item import StageType
from bracket.models.db.stage_item_inputs import StageItemInputFinal
from bracket.models.db.tournament import Tournament
from bracket.models.db.user import UserPublic
from bracket.routes.auth import (
    check_jwt_and_get_user,
    oauth2_scheme,
    user_authenticated_for_tournament,
)
from bracket.routes.models import DataResponse, SuccessResponse
from bracket.sql.rankings import get_ranking_for_stage_item
from bracket.sql.showcase import sql_get_showcase_tournaments, sql_set_showcase_ranking
from bracket.sql.stages import get_full_tournament_details
from bracket.sql.teams import get_teams_with_members
from bracket.sql.users import get_which_clubs_has_user_access_to
from bracket.utils.i18n import tr
from bracket.utils.id_types import TeamId, TournamentId

router = APIRouter(prefix=config.api_prefix)


class ShowcaseParticipant(BaseModel):
    team_id: TeamId
    name: str


class ShowcaseEntry(BaseModel):
    tournament_id: TournamentId
    name: str
    start_time: datetime_utc
    # Participants in finishing order. Empty when nothing has been played yet and no
    # manual placement was entered.
    ranking: list[ShowcaseParticipant]
    # Everyone who took part, for the manual-placement editor.
    participants: list[ShowcaseParticipant]
    # Whether the placement was entered by hand rather than derived from the scores.
    is_manual: bool
    # False for a format the automatic placement does not cover (more than one group,
    # or an elimination bracket) — such a tournament only shows a manual placement.
    has_automatic_ranking: bool
    # Whether the viewer may edit this tournament's placement.
    can_manage: bool


class ShowcaseResponse(DataResponse[list[ShowcaseEntry]]):
    pass


class ShowcaseRankingBody(BaseModel):
    # Team ids in finishing order. An empty list clears the manual placement.
    team_ids: list[TeamId]


async def _optional_user(request: Request) -> UserPublic | None:
    """The logged-in user, or None — the showcase itself is public."""
    try:
        token = await oauth2_scheme(request)
    except HTTPException:
        return None
    if token is None:
        return None
    try:
        return await check_jwt_and_get_user(token)
    except HTTPException:
        return None


async def _automatic_ranking(tournament: Tournament) -> list[TeamId] | None:
    """
    The placement the scores produce, or None for a format that has no single answer.

    Only the single round-robin group case is covered: that is what a drop-in evening
    is, and its standings (points, then the table-tennis tie-break) are exactly what the
    results page shows.
    """
    stages = await get_full_tournament_details(tournament.id, no_draft_rounds=True)
    stage_items = [stage_item for stage in stages for stage_item in stage.stage_items]
    if len(stage_items) != 1 or stage_items[0].type != StageType.ROUND_ROBIN:
        return None

    stage_item = stage_items[0]
    ranking = await get_ranking_for_stage_item(tournament.id, stage_item.id)
    if ranking is None:
        return None

    teams_by_input_id = {
        stage_item_input.id: stage_item_input.team_id
        for stage_item_input in stage_item.inputs
        if isinstance(stage_item_input, StageItemInputFinal)
    }
    return [
        team_id
        for input_id, _ in determine_team_ranking_for_stage_item(stage_item, ranking)
        if (team_id := teams_by_input_id.get(input_id)) is not None
    ]


@router.get("/showcase", response_model=ShowcaseResponse)
async def get_showcase(user: UserPublic | None = Depends(_optional_user)) -> ShowcaseResponse:
    """
    The Ra drop-in series: every public tournament of the series with its placement.

    Public on purpose — the page it feeds is meant to be shared with people who have no
    account.
    """
    club_ids = set(await get_which_clubs_has_user_access_to(user.id)) if user else set()
    entries = []

    for tournament, manual_ranking in await sql_get_showcase_tournaments():
        teams = await get_teams_with_members(tournament.id, only_active_teams=True)
        names_by_team_id = {team.id: team.name for team in teams}
        automatic_ranking = await _automatic_ranking(tournament)

        # A manual placement leads; whoever it does not mention keeps their computed
        # position behind it. That way correcting only the podium is enough.
        manual = [team_id for team_id in manual_ranking or [] if team_id in names_by_team_id]
        rest = [team_id for team_id in automatic_ranking or [] if team_id not in manual]

        entries.append(
            ShowcaseEntry(
                tournament_id=tournament.id,
                name=tournament.name,
                start_time=tournament.start_time,
                ranking=[
                    ShowcaseParticipant(team_id=team_id, name=names_by_team_id[team_id])
                    for team_id in [*manual, *rest]
                ],
                participants=[
                    ShowcaseParticipant(team_id=team.id, name=team.name) for team in teams
                ],
                is_manual=len(manual) > 0,
                has_automatic_ranking=automatic_ranking is not None,
                can_manage=user is not None and (user.is_admin or tournament.club_id in club_ids),
            )
        )

    return ShowcaseResponse(data=entries)


@router.put("/tournaments/{tournament_id}/showcase-ranking", response_model=SuccessResponse)
async def set_showcase_ranking(
    tournament_id: TournamentId,
    body: ShowcaseRankingBody,
    _: UserPublic = Depends(user_authenticated_for_tournament),
) -> SuccessResponse:
    """
    Correct the placement the showcase page shows for this tournament.

    Allowed on an archived tournament: the placement is a display correction, not a
    result — the scores themselves stay frozen.
    """
    teams = await get_teams_with_members(tournament_id, only_active_teams=True)
    team_ids = {team.id for team in teams}
    if unknown := [team_id for team_id in body.team_ids if team_id not in team_ids]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=tr("有选手不属于这场比赛：{ids}").format(ids=unknown),
        )
    if len(set(body.team_ids)) != len(body.team_ids):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=tr("名次里有重复的选手"),
        )

    await sql_set_showcase_ranking(tournament_id, body.team_ids)
    return SuccessResponse()
