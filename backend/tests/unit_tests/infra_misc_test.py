"""Unit tests for bracket.config helpers/branches and bracket.cronjobs.scheduling.

No DB/server: config classes are constructed directly and cronjob coroutines run
against mocked SQL/manager layers.
"""

import asyncio
import importlib.util
from pathlib import Path
from unittest import mock

import pytest
from heliclockter import timedelta

import bracket.config as config_module
import bracket.cronjobs.scheduling as scheduling_module
from bracket.config import (
    DemoConfig,
    DevelopmentConfig,
    ProductionConfig,
    init_sentry,
)
from bracket.cronjobs.scheduling import (
    delete_demo_accounts,
    run_cronjob,
    start_cronjobs,
)
from bracket.models.db.account import UserAccountType


def test_is_cors_enabled_branches() -> None:
    cfg = DevelopmentConfig()  # type: ignore[call-arg]
    cfg.cors_origins = "*"
    assert cfg.is_cors_enabled() is False
    cfg.cors_origins = "https://example.com"
    assert cfg.is_cors_enabled() is True


def test_environment_specific_config_classes_construct() -> None:
    # Covers the per-environment config classes (the match arms in config.py just
    # instantiate one of these).
    assert isinstance(DevelopmentConfig(), DevelopmentConfig)  # type: ignore[call-arg]
    assert isinstance(ProductionConfig(), ProductionConfig)  # type: ignore[call-arg]
    assert isinstance(DemoConfig(), DemoConfig)  # type: ignore[call-arg]


_CONFIG_PATH = Path(config_module.__file__)


def _exec_config_for_environment(env_name: str):
    """Re-exec a fresh copy of bracket/config.py with ENVIRONMENT=<env_name> so the
    corresponding `match environment` arm (lines 85-90) is taken."""
    spec = importlib.util.spec_from_file_location(
        f"bracket._config_probe_{env_name.lower()}", str(_CONFIG_PATH)
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("env_name", ["DEVELOPMENT", "PRODUCTION", "DEMO"])
def test_config_module_selects_config_per_environment(env_name, monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", env_name)
    module = _exec_config_for_environment(env_name)
    assert module.environment is module.Environment[env_name]
    assert isinstance(module.config, module.Config)


def test_init_sentry_initializes_when_dsn_set() -> None:
    with (
        mock.patch.object(config_module.config, "sentry_dsn", "https://example@sentry.io/1"),
        mock.patch.object(config_module.sentry_sdk, "init") as mock_init,
    ):
        init_sentry()
    mock_init.assert_called_once()


def test_init_sentry_noop_when_dsn_absent() -> None:
    with (
        mock.patch.object(config_module.config, "sentry_dsn", None),
        mock.patch.object(config_module.sentry_sdk, "init") as mock_init,
    ):
        init_sentry()
    mock_init.assert_not_called()


async def test_delete_demo_accounts_noop_when_none_expired() -> None:
    with (
        mock.patch.object(scheduling_module, "get_expired_demo_users", return_value=[]),
        mock.patch.object(scheduling_module, "delete_user_and_owned_clubs") as mock_delete,
    ):
        await delete_demo_accounts()
    mock_delete.assert_not_called()


async def test_delete_demo_accounts_deletes_expired() -> None:
    demo_user = mock.Mock()
    demo_user.account_type = UserAccountType.DEMO
    demo_user.id = 123

    with (
        mock.patch.object(scheduling_module, "get_expired_demo_users", return_value=[demo_user]),
        mock.patch.object(scheduling_module, "delete_user_and_owned_clubs") as mock_delete,
    ):
        await delete_demo_accounts()
    mock_delete.assert_awaited_once_with(123)


async def test_run_cronjob_runs_entrypoint_then_loops() -> None:
    calls: list[int] = []

    async def entrypoint() -> None:
        calls.append(1)
        if len(calls) >= 2:
            raise asyncio.CancelledError

    # First sleep returns immediately; the coroutine raises CancelledError on its
    # second run to break out of `while True`.
    with mock.patch.object(scheduling_module.asyncio, "sleep", new=mock.AsyncMock()):
        with pytest.raises(asyncio.CancelledError):
            await run_cronjob(entrypoint, timedelta(seconds=0))

    assert len(calls) == 2


async def test_run_cronjob_swallows_entrypoint_exception() -> None:
    calls: list[int] = []

    async def entrypoint() -> None:
        calls.append(1)
        if len(calls) == 1:
            raise ValueError("boom")
        raise asyncio.CancelledError

    with mock.patch.object(scheduling_module.asyncio, "sleep", new=mock.AsyncMock()):
        with pytest.raises(asyncio.CancelledError):
            await run_cronjob(entrypoint, timedelta(seconds=0))

    # The ValueError on the first iteration was caught/logged; the loop continued.
    assert len(calls) == 2


def test_start_cronjobs_registers_coroutines() -> None:
    added: list = []

    def fake_add(coro) -> None:
        added.append(coro)
        coro.close()  # avoid "coroutine was never awaited" warnings

    with mock.patch.object(
        scheduling_module.AsyncioTasksManager, "add_coroutine", side_effect=fake_add
    ):
        start_cronjobs()

    assert len(added) == len(scheduling_module.CRONJOBS)
