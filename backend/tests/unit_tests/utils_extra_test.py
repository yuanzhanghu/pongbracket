"""
Extra tests for bracket/utils/* utility modules to raise coverage on targeted lines.
"""

from contextlib import asynccontextmanager
from unittest.mock import patch

import asyncpg.exceptions
import pytest

from bracket.config import config
from bracket.utils.db import insert_generic
from bracket.utils.errors import (
    ForeignKey,
    UniqueIndex,
    check_foreign_key_violation,
    check_unique_constraint_violation,
    foreign_key_violation_error_lookup,
    unique_index_violation_error_lookup,
)
from bracket.utils.pydantic import EmptyStrToNone, accept_none_and_empty_str
from bracket.utils.security import hash_password, verify_password, verify_captcha_token


# ------------------------------------------------------------------
# bracket/utils/errors.py — lines 72, 90-98
# ------------------------------------------------------------------


class _FakeUniqueViolationError(asyncpg.exceptions.UniqueViolationError):
    """Subclass of the real asyncpg exception so it matches the except-clause type."""

    def __init__(self, constraint_name: str | None) -> None:
        super().__init__(constraint_name or "")
        self._fake_constraint_name = constraint_name

    def as_dict(self) -> dict[str, str | None]:  # type: ignore[override]
        return {"sqlstate": "23505", "constraint_name": self._fake_constraint_name}


class _FakeFKViolationError(asyncpg.exceptions.ForeignKeyViolationError):
    def __init__(self, constraint_name: str | None) -> None:
        super().__init__(constraint_name or "")
        self._fake_constraint_name = constraint_name

    def as_dict(self) -> dict[str, str | None]:  # type: ignore[override]
        return {"sqlstate": "23503", "constraint_name": self._fake_constraint_name}


def test_check_unique_constraint_violation_re_raises_unexpected() -> None:
    """If the constraint isn't in `expected_violations`, the original exception is re-raised. (line 72)"""
    from fastapi import HTTPException

    err = _FakeUniqueViolationError(UniqueIndex.ix_tournaments_dashboard_endpoint.name)

    with pytest.raises(_FakeUniqueViolationError):
        with check_unique_constraint_violation({UniqueIndex.ix_users_email}):
            raise err

    # When the constraint IS expected, we should get an HTTPException.
    with pytest.raises(HTTPException) as exc_info:
        with check_unique_constraint_violation({UniqueIndex.ix_tournaments_dashboard_endpoint}):
            raise err
    assert exc_info.value.status_code == 400
    assert (
        exc_info.value.detail
        == unique_index_violation_error_lookup[UniqueIndex.ix_tournaments_dashboard_endpoint]
    )


def test_check_foreign_key_violation_re_raises_unexpected() -> None:
    """If the FK isn't in `expected_violations`, the original exception is re-raised. (lines 90-98)"""
    from fastapi import HTTPException

    err = _FakeFKViolationError(ForeignKey.courts_tournament_id_fkey.name)

    with pytest.raises(_FakeFKViolationError):
        with check_foreign_key_violation({ForeignKey.players_tournament_id_fkey}):
            raise err

    # When the FK IS expected, we should get an HTTPException.
    with pytest.raises(HTTPException) as exc_info:
        with check_foreign_key_violation({ForeignKey.courts_tournament_id_fkey}):
            raise err
    assert exc_info.value.status_code == 400
    assert (
        exc_info.value.detail
        == foreign_key_violation_error_lookup[ForeignKey.courts_tournament_id_fkey]
    )


def test_check_unique_constraint_violation_no_constraint_name() -> None:
    """If the constraint name is missing, an AssertionError is raised."""
    err = _FakeUniqueViolationError(None)
    with pytest.raises(AssertionError):
        with check_unique_constraint_violation(set()):
            raise err


def test_check_unique_constraint_violation_unknown_constraint() -> None:
    """If the constraint name is not a known UniqueIndex, an AssertionError is raised."""
    err = _FakeUniqueViolationError("not_a_real_constraint")
    with pytest.raises(AssertionError):
        with check_unique_constraint_violation(set()):
            raise err


def test_check_foreign_key_violation_no_constraint_name() -> None:
    err = _FakeFKViolationError(None)
    with pytest.raises(AssertionError):
        with check_foreign_key_violation(set()):
            raise err


def test_check_foreign_key_violation_unknown_constraint() -> None:
    err = _FakeFKViolationError("not_a_real_fk")
    with pytest.raises(AssertionError):
        with check_foreign_key_violation(set()):
            raise err


# ------------------------------------------------------------------
# bracket/utils/pydantic.py — line 8
# ------------------------------------------------------------------


def test_accept_none_and_empty_str_none() -> None:
    """`None` -> returns None."""
    assert accept_none_and_empty_str(None) is None


def test_accept_none_and_empty_str_empty() -> None:
    """Empty string -> returns None."""
    assert accept_none_and_empty_str("") is None


def test_accept_none_and_empty_str_value_error() -> None:
    """Non-empty value -> raises ValueError. (line 8)"""
    with pytest.raises(ValueError, match="Not an empty str or None"):
        accept_none_and_empty_str("hello")


def test_empty_str_to_none_validator_on_model() -> None:
    """The EmptyStrToNone validator actually works when used in a model."""
    from pydantic import BaseModel

    class M(BaseModel):
        x: EmptyStrToNone  # type: ignore[valid-type]

    assert M(x=None).x is None
    assert M(x="").x is None
    with pytest.raises(ValueError):
        M(x="hello")


# ------------------------------------------------------------------
# bracket/utils/security.py — lines 19-24
# ------------------------------------------------------------------


def test_hash_and_verify_password_roundtrip() -> None:
    """hash_password/verify_password are correctly inverse for each other."""
    pw = "s3cret-passw0rd"
    hashed = hash_password(pw)
    assert hashed != pw
    assert verify_password(pw, hashed) is True
    assert verify_password("wrong", hashed) is False


@pytest.mark.asyncio
async def test_verify_captcha_token_no_secret_returns_true() -> None:
    """When no captcha_secret is configured, the function returns True without HTTP. (lines 19-20)"""
    with patch.object(config, "captcha_secret", None):
        assert await verify_captcha_token("any-token") is True


class _FakeHcaptchaResp:
    """A real-looking async context manager that returns a fixed JSON body."""

    def __init__(self, body: dict[str, bool]) -> None:
        self._body = body

    async def __aenter__(self) -> "_FakeHcaptchaResp":
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def json(self) -> dict[str, bool]:
        return self._body


class _FakeHcaptchaSession:
    """Records the posted payload and returns a fixed JSON response."""

    def __init__(self, body: dict[str, bool]) -> None:
        self.posted: dict[str, str] = {}
        self._body = body

    async def __aenter__(self) -> "_FakeHcaptchaSession":
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    def post(self, url: str, data: dict[str, str]) -> _FakeHcaptchaResp:
        self.posted.update(data)
        return _FakeHcaptchaResp(self._body)


@pytest.mark.asyncio
async def test_verify_captcha_token_with_secret_returns_success() -> None:
    """When captcha_secret is set, the function posts to hcaptcha. (lines 21-24)"""
    fake_session = _FakeHcaptchaSession({"success": True})
    with patch.object(config, "captcha_secret", "some-secret"):
        with patch("bracket.utils.security.aiohttp.ClientSession", lambda: fake_session):
            assert await verify_captcha_token("captcha-blob") is True
    # Verify that the post() received both the response token and the secret.
    assert fake_session.posted["response"] == "captcha-blob"
    assert fake_session.posted["secret"] == "some-secret"


@pytest.mark.asyncio
async def test_verify_captcha_token_with_secret_returns_failure() -> None:
    """When the hcaptcha response says success=False, the function returns False."""
    fake_session = _FakeHcaptchaSession({"success": False})
    with patch.object(config, "captcha_secret", "some-secret"):
        with patch("bracket.utils.security.aiohttp.ClientSession", lambda: fake_session):
            assert await verify_captcha_token("captcha-blob") is False


# ------------------------------------------------------------------
# bracket/utils/db.py — lines 48-50 (insert_generic error path)
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_insert_generic_logs_and_reraises() -> None:
    """When the underlying insert fails, the exception is logged and re-raised. (lines 48-50)"""

    from sqlalchemy import Column, Integer, MetaData, Table

    metadata = MetaData()
    test_table = Table(
        "fake_insert_test",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("name", Integer),
    )

    class DummyModel:
        def __init__(self) -> None:
            self.name = "x"

    class _FailingDB:
        async def execute(self, _query: str) -> int:
            raise RuntimeError("boom")

    with patch("bracket.utils.db.to_string_mapping", lambda _m: {"name": "x"}):
        with pytest.raises(RuntimeError, match="boom"):
            await insert_generic(_FailingDB(), DummyModel(), test_table, DummyModel)  # type: ignore[arg-type]
