import csv
import os
from uuid import uuid4

import aiofiles
import aiofiles.os
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from heliclockter import datetime_utc
from starlette import status as http_status

from bracket.config import config
from bracket.database import database
from bracket.logic.subscriptions import check_requirement
from bracket.logic.teams import get_team_logo_path
from bracket.models.db.player import PlayerBody
from bracket.models.db.team import (
    FullTeamWithPlayers,
    Team,
    TeamBody,
    TeamInsertable,
    TeamMoveBody,
    TeamMultiBody,
)
from bracket.models.db.tournament import Tournament
from bracket.models.db.user import UserPublic
from bracket.routes.auth import (
    user_authenticated_for_tournament,
    user_authenticated_or_public_dashboard,
)
from bracket.routes.models import (
    PaginatedTeams,
    SingleTeamResponse,
    SuccessResponse,
    TeamsWithPlayersResponse,
)
from bracket.routes.util import (
    disallow_archived_tournament,
    disallow_rated_individual_tournament,
    disallow_settled_tournament,
    team_dependency,
    team_with_players_dependency,
)
from bracket.schema import players_x_teams, teams
from bracket.sql.players import (
    get_all_players_in_tournament,
    insert_player,
    sql_delete_player_if_orphaned,
)
from bracket.sql.teams import (
    get_next_team_sort_order,
    get_team_by_id,
    get_team_count,
    get_teams_with_members,
    sql_delete_team,
    swap_team_sort_order,
)
from bracket.sql.validation import check_foreign_keys_belong_to_tournament
from bracket.utils.db import fetch_one_parsed
from bracket.utils.errors import ForeignKey, check_foreign_key_violation
from bracket.utils.i18n import tr
from bracket.utils.id_types import TeamId, TournamentId
from bracket.utils.logging import logger
from bracket.utils.pagination import PaginationTeams
from bracket.utils.types import assert_some

router = APIRouter(prefix=config.api_prefix)


async def ensure_unique_team_name(
    tournament_id: TournamentId, name: str, exclude_team_id: TeamId | None = None
) -> None:
    """Reject a team name already used in this tournament — the schedule, bracket
    and score entry all identify teams by name."""
    for team in await get_teams_with_members(tournament_id):
        if team.name == name and team.id != exclude_team_id:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=tr("队伍名“{name}”已存在").format(name=name),
            )


async def update_team_members(
    team_id: TeamId, tournament_id: TournamentId, player_names: list[str]
) -> None:
    """Sync the team's members to exactly ``player_names`` (direct edit).

    New names create players; removed members are unlinked and their player
    record is deleted when no other team still references it.
    """
    [team] = await get_teams_with_members(tournament_id, team_id=team_id)
    new_names = list(dict.fromkeys(name.strip() for name in player_names if name.strip()))
    current = {player.name: player.id for player in team.players}

    # Remove members no longer in the list
    for name, player_id in current.items():
        if name not in new_names:
            await database.execute(
                query=players_x_teams.delete().where(
                    (players_x_teams.c.player_id == player_id)
                    & (players_x_teams.c.team_id == team_id)
                ),
            )
            await sql_delete_player_if_orphaned(tournament_id, player_id)

    # Add new members
    for name in new_names:
        if name not in current:
            player_id = await insert_player(PlayerBody(name=name, active=True), tournament_id)
            await database.execute(
                query=players_x_teams.insert(),
                values={"team_id": team_id, "player_id": player_id},
            )


@router.get("/tournaments/{tournament_id}/teams", response_model=TeamsWithPlayersResponse)
async def get_teams(
    tournament_id: TournamentId,
    pagination: PaginationTeams = Depends(),
    _: UserPublic = Depends(user_authenticated_or_public_dashboard),
) -> TeamsWithPlayersResponse:
    return TeamsWithPlayersResponse(
        data=PaginatedTeams(
            teams=await get_teams_with_members(tournament_id, pagination=pagination),
            count=await get_team_count(tournament_id),
        )
    )


@router.put("/tournaments/{tournament_id}/teams/{team_id}", response_model=SingleTeamResponse)
async def update_team_by_id(
    tournament_id: TournamentId,
    team_body: TeamBody,
    _: UserPublic = Depends(user_authenticated_for_tournament),
    __: Tournament = Depends(disallow_archived_tournament),
    team: Team = Depends(team_dependency),
) -> SingleTeamResponse:
    await check_foreign_keys_belong_to_tournament(team_body, tournament_id)
    await ensure_unique_team_name(tournament_id, team_body.name, exclude_team_id=team.id)

    await database.execute(
        query=teams.update().where(
            (teams.c.id == team.id) & (teams.c.tournament_id == tournament_id)
        ),
        values=team_body.model_dump(exclude={"player_names"}),
    )
    if team_body.player_names is not None:
        await update_team_members(team.id, tournament_id, team_body.player_names)

    return SingleTeamResponse(
        data=assert_some(
            await fetch_one_parsed(
                database,
                Team,
                teams.select().where(
                    (teams.c.id == team.id) & (teams.c.tournament_id == tournament_id)
                ),
            )
        )
    )


@router.post("/tournaments/{tournament_id}/teams/{team_id}/move", response_model=SuccessResponse)
async def move_team(
    tournament_id: TournamentId,
    body: TeamMoveBody,
    _: UserPublic = Depends(user_authenticated_for_tournament),
    __: Tournament = Depends(disallow_archived_tournament),
    # Rated individual tournaments are ordered by rating and cannot be reordered manually.
    ___: Tournament = Depends(disallow_rated_individual_tournament),
    team: Team = Depends(team_dependency),
) -> SuccessResponse:
    await swap_team_sort_order(tournament_id, team.id, body.direction)
    return SuccessResponse()


@router.post("/tournaments/{tournament_id}/teams/{team_id}/logo", response_model=SingleTeamResponse)
async def update_team_logo(
    tournament_id: TournamentId,
    file: UploadFile | None = None,
    _: UserPublic = Depends(user_authenticated_for_tournament),
    __: Tournament = Depends(disallow_archived_tournament),
    team: Team = Depends(team_dependency),
) -> SingleTeamResponse:
    old_logo_path = await get_team_logo_path(tournament_id, team.id)
    filename: str | None = None
    new_logo_path: str | None = None

    if file:
        assert file.filename is not None
        extension = os.path.splitext(file.filename)[1]
        assert extension in (".png", ".jpg", ".jpeg")

        filename = f"{uuid4()}{extension}"
        new_logo_path = f"static/team-logos/{filename}" if file is not None else None

        if new_logo_path:
            await aiofiles.os.makedirs("static/team-logos", exist_ok=True)
            async with aiofiles.open(new_logo_path, "wb") as f:
                await f.write(await file.read())

    if old_logo_path is not None and old_logo_path != new_logo_path:
        try:
            await aiofiles.os.remove(old_logo_path)
        except Exception as exc:
            logger.error(f"Could not remove logo that should still exist: {old_logo_path}\n{exc}")

    await database.execute(
        teams.update().where(teams.c.id == team.id),
        values={"logo_path": filename},
    )
    return SingleTeamResponse(data=assert_some(await get_team_by_id(team.id, tournament_id)))


@router.delete("/tournaments/{tournament_id}/teams/{team_id}", response_model=SuccessResponse)
async def delete_team(
    tournament_id: TournamentId,
    _: UserPublic = Depends(user_authenticated_for_tournament),
    __: Tournament = Depends(disallow_archived_tournament),
    ___: Tournament = Depends(disallow_settled_tournament),
    team: FullTeamWithPlayers = Depends(team_with_players_dependency),
) -> SuccessResponse:
    with check_foreign_key_violation(
        {
            ForeignKey.stage_item_inputs_team_id_fkey,
            ForeignKey.matches_stage_item_input1_id_fkey,
            ForeignKey.matches_stage_item_input2_id_fkey,
        }
    ):
        await sql_delete_team(tournament_id, team.id)

    # The players_x_teams links cascade away with the team, but the player records
    # themselves do not — clean up the ones no other team still holds.
    for player in team.players:
        await sql_delete_player_if_orphaned(tournament_id, player.id)

    return SuccessResponse()


@router.post("/tournaments/{tournament_id}/teams", response_model=SingleTeamResponse)
async def create_team(
    team_to_insert: TeamBody,
    tournament_id: TournamentId,
    user: UserPublic = Depends(user_authenticated_for_tournament),
    _: Tournament = Depends(disallow_archived_tournament),
    __: Tournament = Depends(disallow_rated_individual_tournament),
) -> SingleTeamResponse:
    await check_foreign_keys_belong_to_tournament(team_to_insert, tournament_id)
    await ensure_unique_team_name(tournament_id, team_to_insert.name)

    existing_teams = await get_teams_with_members(tournament_id)
    check_requirement(existing_teams, user, "max_teams")

    last_record_id = await database.execute(
        query=teams.insert(),
        values=TeamInsertable(
            **team_to_insert.model_dump(exclude={"player_names"}),
            created=datetime_utc.now(),
            tournament_id=tournament_id,
            sort_order=await get_next_team_sort_order(tournament_id),
        ).model_dump(),
    )
    if team_to_insert.player_names is not None:
        await update_team_members(last_record_id, tournament_id, team_to_insert.player_names)

    team_result = await get_team_by_id(last_record_id, tournament_id)
    assert team_result is not None
    return SingleTeamResponse(data=team_result)


@router.post("/tournaments/{tournament_id}/teams_multi", response_model=SuccessResponse)
async def create_multiple_teams(
    team_body: TeamMultiBody,
    tournament_id: TournamentId,
    user: UserPublic = Depends(user_authenticated_for_tournament),
    _: Tournament = Depends(disallow_archived_tournament),
    __: Tournament = Depends(disallow_rated_individual_tournament),
) -> SuccessResponse:
    reader = list(csv.reader(team_body.names.split("\n"), delimiter=","))
    teams_and_players = [
        (row[0], [p for p in row[1:] if len(p) > 0] if len(row) > 1 else [])
        for row in reader
        if len(row) > 0
    ]
    players = [player for row in teams_and_players for player in row[1]]

    existing_teams = await get_teams_with_members(tournament_id)
    existing_players = await get_all_players_in_tournament(tournament_id)

    seen_names = {team.name for team in existing_teams}
    for team_name, _players in teams_and_players:
        if team_name in seen_names:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=tr("队伍名“{name}”已存在").format(name=team_name),
            )
        seen_names.add(team_name)

    check_requirement(existing_teams, user, "max_teams", additions=len(reader))
    check_requirement(existing_players, user, "max_players", additions=len(players))

    next_sort_order = await get_next_team_sort_order(tournament_id)
    async with database.transaction():
        for team_name, players in teams_and_players:
            team_id = await database.execute(
                query=teams.insert(),
                values=TeamInsertable(
                    name=team_name,
                    active=team_body.active,
                    created=datetime_utc.now(),
                    tournament_id=tournament_id,
                    sort_order=next_sort_order,
                ).model_dump(),
            )
            next_sort_order += 1
            for player in players:
                player_body = PlayerBody(name=player, active=team_body.active)
                player_id = await insert_player(player_body, tournament_id)
                await database.execute(
                    query=players_x_teams.insert(),
                    values={"team_id": team_id, "player_id": player_id},
                )

    return SuccessResponse()
