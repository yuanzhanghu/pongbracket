"""Integration tests for the remaining DB-bound paths."""

import pytest

from bracket.logic.tournaments import (
    delete_tournament_logo,
    get_tournament_logo_path,
)
from tests.integration_tests.models import AuthContext


@pytest.mark.asyncio(loop_scope="session")
async def test_get_tournament_logo_path_no_logo(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """get_tournament_logo_path returns None when no logo is set. (lines 14-17)"""
    result = await get_tournament_logo_path(auth_context.tournament.id)
    assert result is None


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_tournament_logo_no_logo(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """delete_tournament_logo is a no-op when no logo exists. (lines 20-23)"""
    await delete_tournament_logo(auth_context.tournament.id)
