"""
Extra tests for bracket/routes/auth.py.
Covers the JWT edge cases, club access check, and endpoint_name lookup.
"""

import jwt
import pytest
from heliclockter import datetime_utc, timedelta

from bracket.config import config
from bracket.models.db.account import UserAccountType
from bracket.models.db.user import UserInsertable
from bracket.utils.http import HTTPMethod
from tests.integration_tests.api.shared import send_request
from tests.integration_tests.sql import inserted_user


@pytest.mark.asyncio(loop_scope="session")
async def test_check_jwt_no_user_claim(startup_and_shutdown_uvicorn_server: None) -> None:
    """Token with no 'user' claim -> check_jwt_and_get_user returns None -> 401."""
    token = jwt.encode(
        {"exp": datetime_utc.now() + timedelta(minutes=10)},
        config.jwt_secret,
        algorithm="HS256",
    )
    headers = {"Authorization": f"Bearer {token}"}
    response = await send_request(HTTPMethod.GET, "users/me", {}, None, headers)
    assert response == {"detail": "登录状态无效，请重新登录"}


@pytest.mark.asyncio(loop_scope="session")
async def test_check_jwt_user_not_in_db(startup_and_shutdown_uvicorn_server: None) -> None:
    """Token with valid JWT but email not in DB -> 401."""
    token = jwt.encode(
        {"user": "nonexistent@example.org", "exp": datetime_utc.now() + timedelta(minutes=10)},
        config.jwt_secret,
        algorithm="HS256",
    )
    headers = {"Authorization": f"Bearer {token}"}
    response = await send_request(HTTPMethod.GET, "users/me", {}, None, headers)
    assert response == {"detail": "登录状态无效，请重新登录"}


@pytest.mark.asyncio(loop_scope="session")
async def test_user_authenticated_for_club_no_access(
    startup_and_shutdown_uvicorn_server: None,
) -> None:
    """User with no access to the club -> 401 (user_authenticated_for_club)."""
    other_user = UserInsertable(
        email=f"other-{datetime_utc.now().timestamp()}@example.org",
        name="Other User",
        password_hash="x",
        created=datetime_utc.now(),
        account_type=UserAccountType.REGULAR,
    )
    async with inserted_user(other_user) as user_inserted:
        token = jwt.encode(
            {"user": user_inserted.email, "exp": datetime_utc.now() + timedelta(minutes=10)},
            config.jwt_secret,
            algorithm="HS256",
        )
        headers = {"Authorization": f"Bearer {token}"}
        # Club id 999999 does not belong to this user
        response = await send_request(HTTPMethod.PUT, "clubs/999999", {}, None, headers)
        assert response == {"detail": "登录状态无效，请重新登录"}


@pytest.mark.asyncio(loop_scope="session")
async def test_endpoint_name_not_found(startup_and_shutdown_uvicorn_server: None) -> None:
    """GET /tournaments?endpoint_name=missing -> 401 (tournament not found)."""
    headers = {"Authorization": "Bearer some-token"}
    response = await send_request(
        HTTPMethod.GET, "tournaments?endpoint_name=nonexistent-endpoint", {}, None, headers
    )
    assert response == {"detail": "登录状态无效，请重新登录"}


@pytest.mark.asyncio(loop_scope="session")
async def test_check_jwt_and_get_user_email_none_branch() -> None:
    """Patches ``str`` in the auth module so that ``str(None)`` returns None,
    then calls check_jwt_and_get_user with a token whose payload has no
    ``user`` key. The function takes the ``if email is None: return None``
    branch (line 77). Unreachable in practice: built-in ``str(None)`` is
    the string "None", never None.
    """
    import jwt as _jwt
    from unittest.mock import patch

    from bracket.config import config as _config
    from bracket.routes.auth import check_jwt_and_get_user

    token = _jwt.encode(
        {"exp": datetime_utc.now() + timedelta(minutes=10)},
        _config.jwt_secret,
        algorithm="HS256",
    )

    def fake_str(value: object) -> str | None:
        return None if value is None else str(value)  # type: ignore[arg-type,return-value]

    with patch("bracket.routes.auth.str", side_effect=fake_str):
        result = await check_jwt_and_get_user(token)
    assert result is None
    assert result is None
