"""
Unit tests for bracket/sql/stage_items.py — specifically line 79:
get_stage_item raises HTTPException when the stage item doesn't exist.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from bracket.sql.stage_items import get_stage_item
from bracket.utils.id_types import StageItemId, TournamentId


@pytest.mark.asyncio
async def test_get_stage_item_raises_when_not_found() -> None:
    """Lines 78-82: HTTPException when get_full_tournament_details returns empty."""
    with patch(
        "bracket.sql.stage_items.get_full_tournament_details",
        AsyncMock(return_value=[]),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await get_stage_item(TournamentId(1), StageItemId(999))
    assert exc_info.value.status_code == 400
    assert "阶段项目不存在" in str(exc_info.value.detail)
