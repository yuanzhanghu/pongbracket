import json

from bracket.database import database
from bracket.models.db.tournament import Tournament
from bracket.utils.id_types import TeamId, TournamentId

# The showcase page lists the Ra drop-in series. The name is typed by hand every week
# ("Ra drop-in", "ra dropin", "Ra drop-in 2026-08-22(转战ottc)"), so the match is made on
# the name with everything but letters and digits stripped out.
SHOWCASE_NAME_FRAGMENT = "radrop"


def parse_showcase_ranking(value: object) -> list[TeamId] | None:
    """The stored JSON array of team ids, or None when there is no manual placement."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, list):
        return None
    return [TeamId(item) for item in parsed if isinstance(item, int)]


async def sql_get_showcase_tournaments() -> list[tuple[Tournament, list[TeamId] | None]]:
    """
    The public tournaments of the showcase series, oldest first, each with its manual
    placement (None when the standings should speak for themselves).

    Only public tournaments are listed: the date links to the results page, which a
    visitor without an account can only open when the tournament is public.
    """
    query = """
        SELECT *
        FROM tournaments
        WHERE dashboard_public IS TRUE
        AND regexp_replace(lower(name), '[^a-z0-9]', '', 'g') LIKE :pattern
        ORDER BY start_time ASC, id ASC
        """
    results = await database.fetch_all(
        query=query, values={"pattern": f"%{SHOWCASE_NAME_FRAGMENT}%"}
    )
    return [
        (
            Tournament.model_validate(result),
            parse_showcase_ranking(result._mapping["showcase_ranking"]),
        )
        for result in results
    ]


async def sql_set_showcase_ranking(
    tournament_id: TournamentId, team_ids: list[TeamId] | None
) -> None:
    query = """
        UPDATE tournaments
        SET showcase_ranking = :showcase_ranking
        WHERE id = :tournament_id
        """
    await database.execute(
        query=query,
        values={
            "tournament_id": tournament_id,
            "showcase_ranking": json.dumps(team_ids) if team_ids else None,
        },
    )
