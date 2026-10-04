"""
Tests for bracket/routes/showcase.py and bracket/sql/showcase.py.

Covers:
- GET /showcase without a login: lists the public tournaments whose name matches the
  series, with the placement their single round-robin group produces
- PUT /tournaments/{id}/showcase-ranking: a manual placement leads, the rest follows
- clearing the manual placement restores the automatic one
- a team from another tournament is rejected
"""

from typing import Any

import pytest

from bracket.sql.shared import sql_delete_stage_item_with_foreign_keys
from bracket.sql.stages import get_full_tournament_details
from bracket.utils.dummy_records import (
    DUMMY_RANKING1,
    DUMMY_STAGE1,
    DUMMY_TEAM1,
    DUMMY_TOURNAMENT,
)
from bracket.utils.http import HTTPMethod
from tests.integration_tests.api.shared import (
    SUCCESS_RESPONSE,
    send_auth_request,
    send_request,
)
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import (
    inserted_ranking,
    inserted_stage,
    inserted_team,
    inserted_tournament,
)


async def _showcase_entry(tournament_id: int) -> dict[str, Any]:
    """The showcase row of one tournament, fetched the way a visitor without an account
    fetches it (no Authorization header)."""
    response = await send_request(HTTPMethod.GET, "showcase")
    entries = [entry for entry in response["data"] if entry["tournament_id"] == tournament_id]
    assert len(entries) == 1, f"tournament {tournament_id} not in the showcase: {response}"
    return entries[0]


@pytest.mark.asyncio(loop_scope="session")
async def test_showcase_lists_series_and_accepts_a_manual_placement(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with (
        inserted_tournament(
            DUMMY_TOURNAMENT.model_copy(
                update={
                    "club_id": auth_context.club.id,
                    "name": "Ra drop-in 2026-08-22",
                    "dashboard_endpoint": None,
                }
            )
        ) as tournament,
        inserted_ranking(DUMMY_RANKING1.model_copy(update={"tournament_id": tournament.id})),
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": tournament.id})
        ) as stage_inserted,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament.id})) as team_1,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament.id})) as team_2,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament.id})) as team_3,
    ):
        await send_auth_request(
            HTTPMethod.POST,
            f"tournaments/{tournament.id}/stage_items/round_robin_groups",
            auth_context,
            json={"stage_id": stage_inserted.id, "group_count": 1, "team_count": 3},
        )
        try:
            entry = await _showcase_entry(tournament.id)
            assert entry["has_automatic_ranking"] is True
            assert entry["is_manual"] is False
            # Anonymous visitors get the table, not the pencil.
            assert entry["can_manage"] is False
            assert {participant["team_id"] for participant in entry["ranking"]} == {
                team_1.id,
                team_2.id,
                team_3.id,
            }

            # Correcting only the winner is enough: everyone else keeps their computed
            # position behind them.
            response = await send_auth_request(
                HTTPMethod.PUT,
                f"tournaments/{tournament.id}/showcase-ranking",
                auth_context,
                json={"team_ids": [team_3.id]},
            )
            assert response == SUCCESS_RESPONSE

            entry = await _showcase_entry(tournament.id)
            assert entry["is_manual"] is True
            ranked_team_ids = [participant["team_id"] for participant in entry["ranking"]]
            assert ranked_team_ids[0] == team_3.id
            assert sorted(ranked_team_ids[1:]) == sorted([team_1.id, team_2.id])

            # An empty list hands the placement back to the scores.
            response = await send_auth_request(
                HTTPMethod.PUT,
                f"tournaments/{tournament.id}/showcase-ranking",
                auth_context,
                json={"team_ids": []},
            )
            assert response == SUCCESS_RESPONSE
            assert (await _showcase_entry(tournament.id))["is_manual"] is False
        finally:
            [stage] = [
                stage
                for stage in await get_full_tournament_details(tournament.id)
                if stage.id == stage_inserted.id
            ]
            for stage_item in stage.stage_items:
                await sql_delete_stage_item_with_foreign_keys(stage_item.id)


@pytest.mark.asyncio(loop_scope="session")
async def test_showcase_ranking_rejects_a_team_from_another_tournament(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with (
        inserted_tournament(
            DUMMY_TOURNAMENT.model_copy(
                update={
                    "club_id": auth_context.club.id,
                    "name": "ra dropin 2026-08-01",
                    "dashboard_endpoint": None,
                }
            )
        ) as tournament,
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as foreign_team,
    ):
        response = await send_auth_request(
            HTTPMethod.PUT,
            f"tournaments/{tournament.id}/showcase-ranking",
            auth_context,
            json={"team_ids": [foreign_team.id]},
        )
        assert "detail" in response
        assert (await _showcase_entry(tournament.id))["is_manual"] is False
