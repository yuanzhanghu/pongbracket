"""
Unit tests for bracket/sql/rounds.py — specifically line 44:
get_round_by_id raises ValueError when the round is not found.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from bracket.sql.rounds import get_round_by_id
from bracket.utils.id_types import RoundId, TournamentId


@pytest.mark.asyncio
async def test_get_round_by_id_raises_when_not_found() -> None:
    """Line 44: ValueError when get_full_tournament_details returns no stages."""
    with patch("bracket.sql.rounds.get_full_tournament_details", AsyncMock(return_value=[])):
        with pytest.raises(ValueError, match="Could not find round"):
            await get_round_by_id(TournamentId(1), RoundId(999))
