from typing import cast

from bracket.database import database
from bracket.logic.ranking.statistics import TeamStatistics
from bracket.models.db.team import FullTeamWithPlayers, Team
from bracket.utils.id_types import StageItemInputId, TeamId, TournamentId
from bracket.utils.pagination import PaginationTeams
from bracket.utils.types import dict_without_none


async def get_teams_by_id(team_ids: set[TeamId], tournament_id: TournamentId) -> list[Team]:
    if len(team_ids) < 1:
        return []

    query = """
        SELECT *
        FROM teams
        WHERE id = any(:team_ids)
        AND tournament_id = :tournament_id
    """
    result = await database.fetch_all(
        query=query, values={"team_ids": team_ids, "tournament_id": tournament_id}
    )
    return [Team.model_validate(team) for team in result]


async def get_team_by_id(team_id: TeamId, tournament_id: TournamentId) -> Team | None:
    result = await get_teams_by_id({team_id}, tournament_id)
    return result[0] if len(result) > 0 else None


async def get_teams_with_members(
    tournament_id: TournamentId,
    *,
    only_active_teams: bool = False,
    team_id: TeamId | None = None,
    pagination: PaginationTeams | None = None,
) -> list[FullTeamWithPlayers]:
    active_team_filter = "AND teams.active IS TRUE" if only_active_teams else ""
    team_id_filter = "AND teams.id = :team_id" if team_id is not None else ""
    limit_filter = "LIMIT :limit" if pagination is not None and pagination.limit is not None else ""
    offset_filter = (
        "OFFSET :offset" if pagination is not None and pagination.offset is not None else ""
    )
    if pagination is None:
        sort = "teams.elo_score DESC, teams.wins DESC, name ASC"
    elif pagination.sort_by == "rating":
        # `rating` is the joined category rating, not a teams column; teams without a
        # rating sort last, ties broken by creation order.
        sort = f"pr.current_rating {pagination.sort_direction} NULLS LAST, teams.id ASC"
    elif pagination.sort_by == "sort_order":
        # Manual team order; ties broken by creation order for a stable sequence.
        sort = f"teams.sort_order {pagination.sort_direction}, teams.id ASC"
    else:
        sort = f"teams.{pagination.sort_by} {pagination.sort_direction}"
    query = f"""
        SELECT
            teams.*,
            to_json(array_agg(p.*)) AS players,
            tu.user_id AS bound_user_id,
            pr.current_rating AS rating,
            pr.status AS rating_status,
            rev.pre_rating AS settled_pre_rating,
            rev.post_rating AS settled_post_rating
        FROM teams
        LEFT JOIN players_x_teams pt on pt.team_id = teams.id
        LEFT JOIN players p on pt.player_id = p.id
        LEFT JOIN teams_x_users tu on tu.team_id = teams.id
        LEFT JOIN player_ratings pr on pr.user_id = tu.user_id
            AND pr.category_id = (
                SELECT rating_category_id FROM tournaments WHERE id = :tournament_id
            )
        -- Settlement ledger for THIS tournament. Settlement is sequential
        -- (see logic/rating/settlement.py): each match uses the player's
        -- immediate rating, so the pre-event rating is the FIRST row's
        -- rating_before and the settled rating is the LAST row's rating_after,
        -- in schedule (re.id) order.
        LEFT JOIN LATERAL (
            SELECT
                (ARRAY_AGG(re.rating_before ORDER BY re.id))[1] AS pre_rating,
                (ARRAY_AGG(re.rating_after ORDER BY re.id DESC))[1] AS post_rating
            FROM rating_events re
            WHERE re.tournament_id = :tournament_id AND re.user_id = tu.user_id
        ) rev ON TRUE
        WHERE teams.tournament_id = :tournament_id
        {active_team_filter}
        {team_id_filter}
        GROUP BY teams.id, tu.user_id, pr.current_rating, pr.status,
                 rev.pre_rating, rev.post_rating
        ORDER BY {sort}
        {limit_filter}
        {offset_filter}
        """
    values = dict_without_none(
        {
            "tournament_id": tournament_id,
            "team_id": team_id,
            "limit": pagination.limit if pagination is not None else None,
            "offset": pagination.offset if pagination is not None else None,
        }
    )
    result = await database.fetch_all(query=query, values=values)
    return [FullTeamWithPlayers.model_validate(x) for x in result]


async def get_team_count(
    tournament_id: TournamentId,
    *,
    only_active_teams: bool = False,
) -> int:
    active_team_filter = "AND teams.active IS TRUE" if only_active_teams else ""
    query = f"""
        SELECT count(*)
        FROM teams
        WHERE teams.tournament_id = :tournament_id
        {active_team_filter}
        """
    values = dict_without_none({"tournament_id": tournament_id})
    return cast("int", await database.fetch_val(query=query, values=values))


async def update_team_stats(
    tournament_id: TournamentId,
    stage_item_input_id: StageItemInputId,
    team_statistics: TeamStatistics,
) -> None:
    query = """
        UPDATE stage_item_inputs
        SET
            wins = :wins,
            draws = :draws,
            losses = :losses,
            points = :points
        WHERE stage_item_inputs.tournament_id = :tournament_id
        AND stage_item_inputs.id = :stage_item_input_id
        """
    await database.execute(
        query=query,
        values={
            "tournament_id": tournament_id,
            "stage_item_input_id": stage_item_input_id,
            "wins": team_statistics.wins,
            "draws": team_statistics.draws,
            "losses": team_statistics.losses,
            "points": float(team_statistics.points),
        },
    )


async def get_next_team_sort_order(tournament_id: TournamentId) -> int:
    """The sort_order to give a newly created team so it lands at the end of the list."""
    return cast(
        "int",
        await database.fetch_val(
            query=(
                "SELECT COALESCE(MAX(sort_order), 0) + 1 FROM teams "
                "WHERE tournament_id = :tournament_id"
            ),
            values={"tournament_id": tournament_id},
        ),
    )


async def swap_team_sort_order(
    tournament_id: TournamentId, team_id: TeamId, direction: str
) -> None:
    """
    Move a team one position up or down in the displayed order. A no-op if the team is
    already at the boundary (no neighbor in that direction).

    The whole tournament is renumbered to 1..N afterwards rather than just swapping two
    sort_order values: legacy rows may share a sort_order (they used to default to 0), and
    swapping equal values would move nothing while picking a "neighbor" that isn't the
    adjacent row on screen. Renumbering by the same (sort_order, id) key the listing uses
    keeps the two in step and heals duplicates on first use.
    """
    ordered = await database.fetch_all(
        query=(
            "SELECT id FROM teams WHERE tournament_id = :tournament_id "
            "ORDER BY sort_order ASC, id ASC"
        ),
        values={"tournament_id": tournament_id},
    )
    team_ids = [row["id"] for row in ordered]
    if team_id not in team_ids:
        return

    index = team_ids.index(team_id)
    target = index - 1 if direction == "up" else index + 1
    if not 0 <= target < len(team_ids):
        return

    team_ids[index], team_ids[target] = team_ids[target], team_ids[index]

    async with database.transaction():
        for position, moved_team_id in enumerate(team_ids, start=1):
            await database.execute(
                query=(
                    "UPDATE teams SET sort_order = :sort_order "
                    "WHERE id = :team_id AND tournament_id = :tournament_id "
                    "AND sort_order IS DISTINCT FROM :sort_order"
                ),
                values={
                    "sort_order": position,
                    "team_id": moved_team_id,
                    "tournament_id": tournament_id,
                },
            )


async def sql_delete_team(tournament_id: TournamentId, team_id: TeamId) -> None:
    query = "DELETE FROM teams WHERE id = :team_id AND tournament_id = :tournament_id"
    await database.fetch_one(
        query=query, values={"team_id": team_id, "tournament_id": tournament_id}
    )


async def sql_delete_teams_of_tournament(tournament_id: TournamentId) -> None:
    query = "DELETE FROM teams WHERE tournament_id = :tournament_id"
    await database.fetch_one(query=query, values={"tournament_id": tournament_id})
