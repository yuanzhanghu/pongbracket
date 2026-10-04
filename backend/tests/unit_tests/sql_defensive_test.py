"""
Unit tests for defensive ValueError checks in bracket/sql/*.py.

These checks fire when database.fetch_one returns None for an INSERT ... RETURNING
or a SELECT that should always return a row. They are unreachable in normal
operation, so we exercise them by mocking database.fetch_one.
"""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest

from bracket.models.db.club import ClubCreateBody
from bracket.models.db.match import MatchCreateBody
from bracket.sql.clubs import create_club
from bracket.sql.matches import sql_create_match, sql_get_match
from bracket.sql.stage_item_inputs import sql_create_stage_item_input
from bracket.sql.stage_items import sql_create_stage_item
from bracket.sql.stages import sql_create_stage
from bracket.utils.id_types import TournamentId, UserId


@asynccontextmanager
async def _null_transaction() -> AsyncMock:
    """Async context manager used to mock database.transaction()."""
    yield


@pytest.mark.asyncio
async def test_create_club_raises_when_insert_returns_none() -> None:
    """bracket/sql/clubs.py line 27: create_club raises ValueError if INSERT
    returns no row (defensive)."""
    with patch("bracket.sql.clubs.database") as mock_db:
        mock_db.transaction = lambda: _null_transaction()
        mock_db.execute = AsyncMock()
        mock_db.fetch_one = AsyncMock(return_value=None)
        with pytest.raises(ValueError, match="Could not create club"):
            await create_club(ClubCreateBody(name="X"), UserId(-1))


@pytest.mark.asyncio
async def test_sql_create_match_raises_when_insert_returns_none() -> None:
    """bracket/sql/matches.py line 83: sql_create_match raises ValueError if
    INSERT returns no row (defensive)."""
    body = MatchCreateBody(
        round_id=-1,  # type: ignore[arg-type]
        court_id=None,
        stage_item_input1_id=None,
        stage_item_input2_id=None,
        stage_item_input1_winner_from_match_id=None,
        stage_item_input2_winner_from_match_id=None,
        duration_minutes=10,
        margin_minutes=5,
        custom_duration_minutes=None,
        custom_margin_minutes=None,
        best_of=3,
    )
    with patch("bracket.sql.matches.database") as mock_db:
        mock_db.fetch_one = AsyncMock(return_value=None)
        with pytest.raises(ValueError, match="Could not create stage"):
            await sql_create_match(body)


@pytest.mark.asyncio
async def test_sql_get_match_raises_when_select_returns_none() -> None:
    """bracket/sql/matches.py line 242: sql_get_match raises ValueError when
    the match id is not found (defensive)."""
    with patch("bracket.sql.matches.database") as mock_db:
        mock_db.fetch_one = AsyncMock(return_value=None)
        with pytest.raises(ValueError, match="Could not create stage"):
            await sql_get_match(-1)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_sql_create_stage_item_raises_when_insert_returns_none() -> None:
    """bracket/sql/stage_items.py line 35: sql_create_stage_item raises
    ValueError if INSERT returns no row (defensive)."""
    from bracket.models.db.stage_item import StageItemCreateBody, StageType

    body = StageItemCreateBody(
        stage_id=-1,  # type: ignore[arg-type]
        type=StageType.ROUND_ROBIN,
        team_count=2,
        name="X",
        ranking_id=-1,  # type: ignore[arg-type]
    )
    with patch("bracket.sql.stage_items.database") as mock_db:
        mock_db.fetch_one = AsyncMock(return_value=None)
        with pytest.raises(ValueError, match="Could not create stage"):
            await sql_create_stage_item(TournamentId(-1), body)


@pytest.mark.asyncio
async def test_sql_create_stage_item_input_raises_when_insert_returns_none() -> None:
    """bracket/sql/stage_item_inputs.py line 132: sql_create_stage_item_input
    raises ValueError if INSERT returns no row (defensive)."""
    from bracket.models.db.stage_item_inputs import StageItemInputCreateBodyEmpty

    with patch("bracket.sql.stage_item_inputs.database") as mock_db:
        mock_db.fetch_one = AsyncMock(return_value=None)
        with pytest.raises(ValueError, match="Could not create stage"):
            await sql_create_stage_item_input(
                TournamentId(-1),
                -1,  # type: ignore[arg-type]
                StageItemInputCreateBodyEmpty(slot=1),
            )


@pytest.mark.asyncio
async def test_sql_create_stage_raises_when_insert_returns_none() -> None:
    """bracket/sql/stages.py line 147: sql_create_stage raises ValueError if
    INSERT returns no row (defensive)."""
    with patch("bracket.sql.stages.database") as mock_db:
        mock_db.fetch_one = AsyncMock(return_value=None)
        with pytest.raises(ValueError, match="Could not create stage"):
            await sql_create_stage(TournamentId(-1))
