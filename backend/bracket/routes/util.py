from fastapi import HTTPException
from sqlalchemy import select
from starlette import status

from bracket.database import database
from bracket.models.db.match import Match
from bracket.models.db.round import Round
from bracket.models.db.team import FullTeamWithPlayers, Team
from bracket.models.db.tournament import Tournament, TournamentStatus
from bracket.models.db.util import RoundWithMatches, StageItemWithRounds, StageWithStageItems
from bracket.schema import matches, rounds, stage_items, stages, teams
from bracket.sql.rounds import get_round_by_id
from bracket.sql.stage_items import get_stage_item
from bracket.sql.stages import get_full_tournament_details
from bracket.sql.teams import get_teams_with_members
from bracket.sql.tournaments import sql_get_tournament
from bracket.utils.db import fetch_one_parsed
from bracket.utils.i18n import tr
from bracket.utils.id_types import MatchId, RoundId, StageId, StageItemId, TeamId, TournamentId


async def round_dependency(tournament_id: TournamentId, round_id: RoundId) -> Round:
    round_ = await fetch_one_parsed(
        database,
        Round,
        rounds.select().where(
            (rounds.c.id == round_id)
            & rounds.c.stage_item_id.in_(
                select(stage_items.c.id)
                .join(stages, stage_items.c.stage_id == stages.c.id)
                .where(stages.c.tournament_id == tournament_id)
            )
        ),
    )

    if round_ is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=tr("找不到 ID 为 {id} 的回合").format(id=round_id),
        )

    return round_


async def round_with_matches_dependency(
    tournament_id: TournamentId, round_id: RoundId
) -> RoundWithMatches:
    return await get_round_by_id(tournament_id, round_id)


async def stage_dependency(tournament_id: TournamentId, stage_id: StageId) -> StageWithStageItems:
    stages = await get_full_tournament_details(
        tournament_id, no_draft_rounds=False, stage_id=stage_id
    )

    if len(stages) < 1:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=tr("找不到 ID 为 {id} 的阶段").format(id=stage_id),
        )

    return stages[0]


async def stage_item_dependency(
    tournament_id: TournamentId, stage_item_id: StageItemId
) -> StageItemWithRounds:
    return await get_stage_item(tournament_id, stage_item_id=stage_item_id)


async def match_dependency(tournament_id: TournamentId, match_id: MatchId) -> Match:
    match = await fetch_one_parsed(
        database,
        Match,
        matches.select().where(
            (matches.c.id == match_id)
            & matches.c.round_id.in_(
                select(rounds.c.id)
                .join(stage_items, rounds.c.stage_item_id == stage_items.c.id)
                .join(stages, stage_items.c.stage_id == stages.c.id)
                .where(stages.c.tournament_id == tournament_id)
            )
        ),
    )

    if match is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=tr("找不到 ID 为 {id} 的对阵").format(id=match_id),
        )

    return match


async def team_dependency(tournament_id: TournamentId, team_id: TeamId) -> Team:
    team = await fetch_one_parsed(
        database,
        Team,
        teams.select().where((teams.c.id == team_id) & (teams.c.tournament_id == tournament_id)),
    )

    if team is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=tr("找不到 ID 为 {id} 的队伍").format(id=team_id),
        )

    return team


async def team_with_players_dependency(
    tournament_id: TournamentId, team_id: TeamId
) -> FullTeamWithPlayers:
    teams_with_members = await get_teams_with_members(tournament_id, team_id=team_id)

    if len(teams_with_members) < 1:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=tr("找不到 ID 为 {id} 的队伍").format(id=team_id),
        )

    return teams_with_members[0]


async def disallow_archived_tournament(tournament_id: TournamentId) -> Tournament:
    tournament = await sql_get_tournament(tournament_id)
    if tournament.status is TournamentStatus.ARCHIVED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=tr("已归档的比赛不能修改"),
            headers={"WWW-Authenticate": "Bearer"},
        )

    return tournament


async def disallow_settled_tournament(tournament_id: TournamentId) -> Tournament:
    """Block destructive changes once a tournament's rating ledger is settled."""
    tournament = await sql_get_tournament(tournament_id)
    if tournament.settled_seq is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=tr("赛事已结算；请先撤销结算再删除或修改"),
            headers={"WWW-Authenticate": "Bearer"},
        )

    return tournament


async def disallow_rated_individual_tournament(tournament_id: TournamentId) -> Tournament:
    """Block free-text team creation only on *rated* individual tournaments.

    In a rated individual tournament every team must be one bound account, so
    teams are created only by admitting a registered account (join-request
    approval or a trusted-manager direct add) — never by typing a team name.
    This keeps the one-team-one-account binding intact and prevents unbound
    teams that would later block settlement.

    Non-rated individual tournaments and team tournaments are unaffected: there
    the creator may type a free-text team name (not bound to any account).
    """
    tournament = await sql_get_tournament(tournament_id)
    if tournament.is_individual and tournament.rating_category_id is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=tr(
                "个人积分赛只能通过选择已注册账号来添加参赛者（报名申请或直接添加），不能手动输入队伍名称"
            ),
            headers={"WWW-Authenticate": "Bearer"},
        )

    return tournament
