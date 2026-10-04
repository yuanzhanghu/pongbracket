from typing import Any, Literal

from bracket.database import database
from bracket.models.db.tournament import (
    Tournament,
    TournamentBody,
    TournamentChangeStatusBody,
    TournamentUpdateBody,
)
from bracket.utils.id_types import TournamentId


async def sql_get_tournament(tournament_id: TournamentId) -> Tournament:
    query = """
        SELECT *
        FROM tournaments
        WHERE id = :tournament_id
        """
    result = await database.fetch_one(query=query, values={"tournament_id": tournament_id})
    assert result is not None
    return Tournament.model_validate(result)


async def sql_get_tournament_is_individual(tournament_id: TournamentId) -> bool:
    """Whether this tournament's participants are individuals rather than teams.

    Read on its own (instead of via `sql_get_tournament`) because it is resolved for every
    request that addresses a tournament, only to pick the wording of its messages.
    """
    query = """
        SELECT is_individual
        FROM tournaments
        WHERE id = :tournament_id
        """
    return bool(await database.fetch_val(query=query, values={"tournament_id": tournament_id}))


async def sql_get_public_tournament_name(tournament_id: TournamentId) -> str | None:
    """Name of a tournament anyone may view, for the shared link's page title.

    Returns None for a private or non-existent tournament, so the HTML served to a
    link preview crawler never names a tournament its reader could not open anyway.
    """
    query = """
        SELECT name
        FROM tournaments
        WHERE id = :tournament_id
        AND dashboard_public IS TRUE
        """
    name = await database.fetch_val(query=query, values={"tournament_id": tournament_id})
    return str(name) if name is not None else None


async def sql_get_tournament_by_endpoint_name(endpoint_name: str) -> Tournament | None:
    # Resolve a public dashboard either by its custom slug (dashboard_endpoint)
    # or by its numeric id, so the /tournaments/{id}/dashboard URL works even
    # when no custom endpoint slug has been set. A custom slug takes precedence.
    query = """
        SELECT *
        FROM tournaments
        WHERE (dashboard_endpoint = :endpoint_name OR CAST(id AS TEXT) = :endpoint_name)
        AND dashboard_public IS TRUE
        ORDER BY (dashboard_endpoint = :endpoint_name) DESC
        LIMIT 1
        """
    result = await database.fetch_one(query=query, values={"endpoint_name": endpoint_name})
    return Tournament.model_validate(result) if result is not None else None


async def sql_get_tournaments(
    club_ids: tuple[int, ...],
    endpoint_name: str | None = None,
    filter_: Literal["ALL", "OPEN", "ARCHIVED"] = "ALL",
) -> list[Tournament]:
    query = """
        SELECT *
        FROM tournaments
        WHERE club_id = any(:club_ids)
        """

    params: dict[str, Any] = {"club_ids": club_ids}

    if endpoint_name is not None:
        query += "AND dashboard_endpoint = :endpoint_name"
        params = {**params, "endpoint_name": endpoint_name}

    if filter_ == "OPEN":
        query += "AND status = 'OPEN'"
    elif filter_ == "ARCHIVED":
        query += "AND status = 'ARCHIVED'"

    result = await database.fetch_all(query=query, values=params)
    return [Tournament.model_validate(x) for x in result]


async def sql_delete_tournament(tournament_id: TournamentId) -> None:
    query = """
        DELETE FROM tournaments
        WHERE id = :tournament_id
        """
    await database.fetch_one(query=query, values={"tournament_id": tournament_id})


async def sql_update_tournament(
    tournament_id: TournamentId, tournament: TournamentUpdateBody
) -> None:
    query = """
        UPDATE tournaments
        SET
            start_time = :start_time,
            name = :name,
            dashboard_public = :dashboard_public,
            dashboard_endpoint = :dashboard_endpoint,
            players_can_be_in_multiple_teams = :players_can_be_in_multiple_teams,
            auto_assign_courts = :auto_assign_courts,
            duration_minutes = :duration_minutes,
            margin_minutes = :margin_minutes
        WHERE tournaments.id = :tournament_id
        """
    await database.execute(
        query=query,
        values={"tournament_id": tournament_id, **tournament.model_dump()},
    )


async def sql_update_tournament_status(
    tournament_id: TournamentId, body: TournamentChangeStatusBody
) -> None:
    query = """
        UPDATE tournaments
        SET status = :state
        WHERE tournaments.id = :tournament_id
        """

    # Archiving only freezes writes; it leaves dashboard_public alone, so a finished
    # tournament keeps the shared results link its spectators already have.
    params = {"tournament_id": tournament_id, "state": body.status.value}
    await database.execute(query=query, values=params)


async def sql_create_tournament(tournament: TournamentBody) -> TournamentId:
    query = """
        INSERT INTO tournaments (
            name,
            start_time,
            club_id,
            dashboard_public,
            dashboard_endpoint,
            logo_path,
            players_can_be_in_multiple_teams,
            auto_assign_courts,
            duration_minutes,
            margin_minutes,
            is_individual,
            rating_category_id
        )
        VALUES (
            :name,
            :start_time,
            :club_id,
            :dashboard_public,
            :dashboard_endpoint,
            :logo_path,
            :players_can_be_in_multiple_teams,
            :auto_assign_courts,
            :duration_minutes,
            :margin_minutes,
            :is_individual,
            :rating_category_id
        )
        RETURNING id
        """
    # rating_category_id is None for non-rated tournaments; model_dump drops None
    # values, so set the two rating columns explicitly to keep the named params present.
    values = {
        **tournament.model_dump(),
        "is_individual": tournament.is_individual,
        "rating_category_id": tournament.rating_category_id,
    }
    new_id = await database.fetch_val(query=query, values=values)
    return TournamentId(new_id)
