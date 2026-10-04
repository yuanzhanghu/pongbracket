from heliclockter import datetime_utc

from bracket.database import database
from bracket.logic.ranking.statistics import START_ELO
from bracket.models.db.player import Player, PlayerBody, PlayerToInsert
from bracket.schema import players
from bracket.utils.id_types import PlayerId, TeamId, TournamentId
from bracket.utils.pagination import PaginationPlayers
from bracket.utils.types import dict_without_none


async def get_all_players_in_tournament(
    tournament_id: TournamentId,
    *,
    not_in_team: bool = False,
    pagination: PaginationPlayers | None = None,
) -> list[Player]:
    # Membership lives in players_x_teams; the players table has no team column.
    not_in_team_filter = (
        "AND NOT EXISTS (SELECT 1 FROM players_x_teams WHERE player_id = players.id)"
        if not_in_team
        else ""
    )
    limit_filter = "LIMIT :limit" if pagination is not None and pagination.limit is not None else ""
    offset_filter = (
        "OFFSET :offset" if pagination is not None and pagination.offset is not None else ""
    )
    sort_by = pagination.sort_by if pagination is not None else "name"
    sort_direction = pagination.sort_direction if pagination is not None else ""
    query = f"""
        SELECT *
        FROM players
        WHERE players.tournament_id = :tournament_id
        {not_in_team_filter}
        ORDER BY {sort_by} {sort_direction}
        {limit_filter}
        {offset_filter}
        """

    result = await database.fetch_all(
        query=query,
        values=dict_without_none(
            {
                "tournament_id": tournament_id,
                "offset": pagination.offset if pagination is not None else None,
                "limit": pagination.limit if pagination is not None else None,
            }
        ),
    )

    return [Player.model_validate(x) for x in result]


async def get_player_by_id(player_id: PlayerId, tournament_id: TournamentId) -> Player | None:
    query = """
        SELECT *
        FROM players
        WHERE id = :player_id
        AND tournament_id = :tournament_id
    """
    result = await database.fetch_one(
        query=query, values={"player_id": player_id, "tournament_id": tournament_id}
    )
    return Player.model_validate(result) if result is not None else None


async def get_player_count(
    tournament_id: TournamentId,
    *,
    not_in_team: bool = False,
) -> int:
    # Membership lives in players_x_teams; the players table has no team column.
    not_in_team_filter = (
        "AND NOT EXISTS (SELECT 1 FROM players_x_teams WHERE player_id = players.id)"
        if not_in_team
        else ""
    )
    query = f"""
        SELECT count(*)
        FROM players
        WHERE players.tournament_id = :tournament_id
        {not_in_team_filter}
        """
    return int(await database.fetch_val(query=query, values={"tournament_id": tournament_id}))


async def sql_delete_player(tournament_id: TournamentId, player_id: PlayerId) -> None:
    query = "DELETE FROM players WHERE id = :player_id AND tournament_id = :tournament_id"
    await database.fetch_one(
        query=query, values={"player_id": player_id, "tournament_id": tournament_id}
    )


async def get_player_ids_in_team(team_id: TeamId) -> list[PlayerId]:
    rows = await database.fetch_all(
        "SELECT player_id FROM players_x_teams WHERE team_id = :team_id", {"team_id": team_id}
    )
    return [PlayerId(row["player_id"]) for row in rows]


async def sql_delete_player_if_orphaned(tournament_id: TournamentId, player_id: PlayerId) -> None:
    """Drop the player record once no team references it anymore.

    Players only exist as team members — there is no page to manage them on their
    own, so an orphan would linger in the tournament forever.
    """
    remaining = await database.fetch_val(
        "SELECT count(*) FROM players_x_teams WHERE player_id = :player_id",
        {"player_id": player_id},
    )
    if remaining == 0:
        await sql_delete_player(tournament_id, player_id)


async def sql_delete_players_of_tournament(tournament_id: TournamentId) -> None:
    query = "DELETE FROM players WHERE tournament_id = :tournament_id"
    await database.fetch_one(query=query, values={"tournament_id": tournament_id})


async def insert_player(player_body: PlayerBody, tournament_id: TournamentId) -> PlayerId:
    player_id = await database.execute(
        query=players.insert(),
        values=PlayerToInsert(
            **player_body.model_dump(),
            created=datetime_utc.now(),
            tournament_id=tournament_id,
            elo_score=START_ELO,
        ).model_dump(),
    )
    return PlayerId(player_id)
