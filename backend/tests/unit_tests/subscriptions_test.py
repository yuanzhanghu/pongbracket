import pytest
from fastapi import HTTPException

from bracket.logic.subscriptions import check_requirement
from bracket.models.db.account import UserAccountType
from bracket.models.db.user import UserInDB
from bracket.utils.id_types import UserId
from tests.integration_tests.mocks import MOCK_NOW


def _make_user(account_type: UserAccountType) -> UserInDB:
    return UserInDB(
        email="test@example.com",
        name="Tester",
        created=MOCK_NOW,
        account_type=account_type,
        id=UserId(-1),
        password_hash="x",
    )


def test_check_requirement_within_bounds_demo() -> None:
    """The DEMO subscription allows up to 8 teams, so 7+1==8 is the exact limit (not exceeded)."""
    user = _make_user(UserAccountType.DEMO)
    check_requirement(
        array=[object()] * 7,
        user=user,
        attribute="max_teams",
        additions=1,
    )


def test_check_requirement_exceeds_demo_limit() -> None:
    user = _make_user(UserAccountType.DEMO)
    with pytest.raises(HTTPException) as exc_info:
        check_requirement(
            array=[object()] * 8,
            user=user,
            attribute="max_teams",
            additions=1,
        )
    assert exc_info.value.status_code == 400
    assert "teams" in exc_info.value.detail


def test_check_requirement_exceeds_regular_limit() -> None:
    user = _make_user(UserAccountType.REGULAR)
    with pytest.raises(HTTPException) as exc_info:
        check_requirement(
            array=[object()] * 128,
            user=user,
            attribute="max_teams",
            additions=1,
        )
    assert exc_info.value.status_code == 400
    assert "128" in exc_info.value.detail


def test_check_requirement_default_additions() -> None:
    """When `additions` is omitted, it defaults to 1."""
    user = _make_user(UserAccountType.DEMO)
    with pytest.raises(HTTPException):
        check_requirement(
            array=[object()] * 8,
            user=user,
            attribute="max_teams",
        )
