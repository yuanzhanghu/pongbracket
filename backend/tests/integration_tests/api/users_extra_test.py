"""
Extra tests for bracket/routes/users.py.
Covers the 401/400 error branches: wrong user_id, registration disabled,
captcha failure, and duplicate email.
"""

from collections.abc import Generator
from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

import pytest
from heliclockter import datetime_utc

from bracket.models.db.account import UserAccountType
from bracket.models.db.user import UserInsertable
from bracket.utils.http import HTTPMethod
from tests.integration_tests.api.shared import send_auth_request, send_request
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import inserted_user


@pytest.mark.asyncio(loop_scope="session")
async def test_get_user_wrong_user_id(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    response = await send_auth_request(
        HTTPMethod.GET, f"users/{auth_context.user.id + 999}", auth_context, {}
    )
    assert response == {"detail": "无权查看该用户信息"}


@pytest.mark.asyncio(loop_scope="session")
async def test_update_user_wrong_user_id(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    response = await send_auth_request(
        HTTPMethod.PUT,
        f"users/{auth_context.user.id + 999}",
        auth_context,
        json={"email": "x@x.com", "name": "x"},
    )
    assert response == {"detail": "无权修改该用户信息"}


@pytest.mark.asyncio(loop_scope="session")
async def test_update_password_wrong_user_id(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    response = await send_auth_request(
        HTTPMethod.PUT,
        f"users/{auth_context.user.id + 999}/password",
        auth_context,
        json={"password": "newpassword"},
    )
    assert response == {"detail": "无权修改该用户信息"}


@contextmanager
def mock_registration_disabled() -> Generator[None]:
    with patch("bracket.routes.users.config.allow_user_registration", False):
        yield


@contextmanager
def mock_demo_registration_disabled() -> Generator[None]:
    with patch("bracket.routes.users.config.allow_demo_user_registration", False):
        yield


@contextmanager
def mock_captcha_invalid() -> Generator[None]:
    with patch(
        "bracket.routes.users.verify_captcha_token",
        AsyncMock(return_value=False),
    ):
        yield


@pytest.mark.asyncio(loop_scope="session")
async def test_register_user_disabled(startup_and_shutdown_uvicorn_server: None) -> None:
    body = {
        "name": "Test",
        "email": "disabled@example.com",
        "password": "mypassword",
        "captcha_token": "token",
    }
    with mock_registration_disabled():
        response = await send_request(HTTPMethod.POST, "users/register", None, body)
    assert response == {"detail": "当前暂不开放注册"}


@pytest.mark.asyncio(loop_scope="session")
async def test_register_user_captcha_invalid(startup_and_shutdown_uvicorn_server: None) -> None:
    body = {
        "name": "Test",
        "email": "captcha@example.com",
        "password": "mypassword",
        "captcha_token": "token",
    }
    with mock_captcha_invalid():
        response = await send_request(HTTPMethod.POST, "users/register", None, body)
    assert response == {"detail": "人机验证失败"}


@pytest.mark.asyncio(loop_scope="session")
async def test_register_user_email_in_use(startup_and_shutdown_uvicorn_server: None) -> None:
    existing_email = f"taken-{datetime_utc.now().timestamp()}@example.org"
    new_user = UserInsertable(
        email=existing_email,
        name="Existing",
        password_hash="x",
        created=datetime_utc.now(),
        account_type=UserAccountType.REGULAR,
    )
    async with inserted_user(new_user):
        body = {
            "name": "Test",
            "email": existing_email,
            "password": "mypassword",
            "captcha_token": "token",
        }
        response = await send_request(HTTPMethod.POST, "users/register", None, body)
    assert response == {"detail": "该邮箱已被使用"}


@pytest.mark.asyncio(loop_scope="session")
async def test_register_demo_user_disabled(startup_and_shutdown_uvicorn_server: None) -> None:
    with mock_demo_registration_disabled():
        response = await send_request(
            HTTPMethod.POST, "users/register_demo", None, {"captcha_token": "token"}
        )
    assert response == {"detail": "当前暂不开放演示账户"}


@pytest.mark.asyncio(loop_scope="session")
async def test_register_demo_user_captcha_invalid(
    startup_and_shutdown_uvicorn_server: None,
) -> None:
    with mock_captcha_invalid():
        response = await send_request(
            HTTPMethod.POST, "users/register_demo", None, {"captcha_token": "token"}
        )
    assert response == {"detail": "人机验证失败"}


@pytest.mark.asyncio(loop_scope="session")
async def test_register_demo_user_email_in_use(startup_and_shutdown_uvicorn_server: None) -> None:
    # Extremely unlikely (uuid4-based email) but exercise the branch
    from bracket.routes import users as users_route

    with patch.object(users_route, "check_whether_email_is_in_use", AsyncMock(return_value=True)):
        response = await send_request(
            HTTPMethod.POST, "users/register_demo", None, {"captcha_token": "token"}
        )
    assert response == {"detail": "该邮箱已被使用"}
