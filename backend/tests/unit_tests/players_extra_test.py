"""
Unit tests for bracket/sql/players.py — specifically get_player_by_id (lines 52-61).

We mock `bracket.database` so the tests stay in-process and fast.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from bracket.sql.players import get_player_by_id
from bracket.utils.dummy_records import DUMMY_MOCK_TIME
from bracket.utils.id_types import PlayerId, TournamentId


@pytest.mark.asyncio
async def test_get_player_by_id_returns_player() -> None:
    """Lines 52-61: get_player_by_id returns a Player when the row exists."""
    fake_row = {
        "id": 1,
        "tournament_id": 1,
        "name": "Alice",
        "active": True,
        "created": DUMMY_MOCK_TIME,
        "elo_score": "1200",
        "wins": 0,
        "draws": 0,
        "losses": 0,
        "team_id": None,
    }
    with patch("bracket.sql.players.database") as mock_db:
        mock_db.fetch_one = AsyncMock(return_value=fake_row)
        result = await get_player_by_id(PlayerId(1), TournamentId(1))
    assert result is not None
    assert result.id == PlayerId(1)
    assert result.name == "Alice"


@pytest.mark.asyncio
async def test_get_player_by_id_returns_none_when_missing() -> None:
    """Lines 58-61: get_player_by_id returns None when fetch_one returns None."""
    with patch("bracket.sql.players.database") as mock_db:
        mock_db.fetch_one = AsyncMock(return_value=None)
        result = await get_player_by_id(PlayerId(999), TournamentId(1))
    assert result is None
