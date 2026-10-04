"""
Unit tests for bracket/sql/tournaments.py — specifically lines 49-50 and 55
of sql_get_tournaments (endpoint_name and ARCHIVED filter branches).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from bracket.sql.tournaments import sql_get_tournaments
from bracket.utils.dummy_records import DUMMY_MOCK_TIME


def _fake_tournament_row() -> dict:
    return {
        "id": 1,
        "club_id": 1,
        "name": "T",
        "created": DUMMY_MOCK_TIME,
        "start_time": DUMMY_MOCK_TIME,
        "dashboard_public": True,
        "dashboard_endpoint": "endpoint-test",
        "logo_path": None,
        "players_can_be_in_multiple_teams": True,
        "auto_assign_courts": True,
        "duration_minutes": 10,
        "margin_minutes": 5,
        "status": "OPEN",
    }


@pytest.mark.asyncio
async def test_sql_get_tournaments_with_endpoint_name() -> None:
    """Lines 48-50: endpoint_name is not None adds the AND clause and param."""
    with patch("bracket.sql.tournaments.database") as mock_db:
        mock_db.fetch_all = AsyncMock(return_value=[])
        result = await sql_get_tournaments((1,), endpoint_name="endpoint-test", filter_="ALL")
    assert result == []
    # Verify the query contained the endpoint_name clause and the params included it.
    call = mock_db.fetch_all.call_args
    query = call.kwargs["query"]
    values = call.kwargs["values"]
    assert "dashboard_endpoint = :endpoint_name" in query
    assert values["endpoint_name"] == "endpoint-test"


@pytest.mark.asyncio
async def test_sql_get_tournaments_archived_filter() -> None:
    """Line 55: filter_='ARCHIVED' adds the AND status = 'ARCHIVED' clause."""
    with patch("bracket.sql.tournaments.database") as mock_db:
        mock_db.fetch_all = AsyncMock(return_value=[])
        result = await sql_get_tournaments((1,), filter_="ARCHIVED")
    assert result == []
    call = mock_db.fetch_all.call_args
    query = call.kwargs["query"]
    assert "status = 'ARCHIVED'" in query


@pytest.mark.asyncio
async def test_sql_get_tournaments_returns_parsed_rows() -> None:
    """Sanity: rows are parsed into Tournament models."""
    with patch("bracket.sql.tournaments.database") as mock_db:
        mock_db.fetch_all = AsyncMock(return_value=[_fake_tournament_row()])
        result = await sql_get_tournaments((1,), filter_="ALL")
    assert len(result) == 1
    assert result[0].name == "T"
