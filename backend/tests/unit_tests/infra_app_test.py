"""Unit tests for bracket.app: the frontend-serving block and lifespan branches.

The frontend block and the production lifespan branches only run when
config.serve_frontend / a non-CI environment are set. To avoid clobbering the
shared `bracket.app` module in sys.modules, we exec a FRESH copy of bracket/app.py
under a throwaway module name.
"""

import importlib.util
import os
from pathlib import Path
from unittest import mock

import pytest
from fastapi.responses import FileResponse
from starlette.responses import HTMLResponse

import bracket.app as app_module
import bracket.config as config_module
from bracket.config import Environment

_APP_PATH = Path(app_module.__file__)


def _load_fresh_app(module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, str(_APP_PATH))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def frontend_dist(tmp_path, monkeypatch):
    """Create a temp frontend-dist/ dir and cwd into it so Path('frontend-dist') resolves."""
    dist = tmp_path / "frontend-dist"
    sub = dist / "assets"
    sub.mkdir(parents=True)
    (dist / "index.html").write_text("<html><head><title>加华积分网</title></head></html>")
    (sub / "app.js").write_text("console.log('hi')")

    # The app module body mounts StaticFiles(directory="static") at import time.
    (tmp_path / "static").mkdir()

    monkeypatch.chdir(tmp_path)
    return dist


def _patch_router_prefixes(monkeypatch, prefix: str) -> None:
    """The app body asserts every router's prefix equals config.api_prefix. The routers
    are shared singletons created at import with the CI prefix (""); align them with the
    test prefix so the assertion passes when serving the frontend."""
    from bracket import routes

    for name in (
        "auth",
        "clubs",
        "courts",
        "favorites",
        "internals",
        "matches",
        "participants",
        "players",
        "rankings",
        "ratings",
        "rounds",
        "showcase",
        "stage_item_inputs",
        "stage_items",
        "stages",
        "teams",
        "tournaments",
        "users",
    ):
        router = getattr(getattr(routes, name), "router")
        monkeypatch.setattr(router, "prefix", prefix)


async def test_frontend_block_serves_files_and_falls_back_to_index(
    frontend_dist, monkeypatch
) -> None:
    monkeypatch.setattr(config_module.config, "serve_frontend", True)
    monkeypatch.setattr(config_module.config, "api_prefix", "/api")
    _patch_router_prefixes(monkeypatch, "/api")

    module = _load_fresh_app("bracket._app_frontend_probe")

    # Existing real sub-file -> served directly.
    served = await module.frontend("assets/app.js")
    assert isinstance(served, FileResponse)
    assert str(served.path).endswith(os.path.join("frontend-dist", "assets", "app.js"))

    # index.html -> served directly.
    index = await module.frontend("index.html")
    assert isinstance(index, FileResponse)

    # Non-existent path -> falls back to index.html.
    fallback = await module.frontend("does-not-exist")
    assert isinstance(fallback, FileResponse)
    assert str(fallback.path).endswith(os.path.join("frontend-dist", "index.html"))


async def test_frontend_names_public_tournament_in_the_served_html(
    frontend_dist, monkeypatch
) -> None:
    """A link preview crawler runs no JavaScript, so the shared card reads this HTML."""
    monkeypatch.setattr(config_module.config, "serve_frontend", True)
    monkeypatch.setattr(config_module.config, "api_prefix", "/api")
    _patch_router_prefixes(monkeypatch, "/api")

    module = _load_fresh_app("bracket._app_frontend_probe_title")
    lookup = mock.AsyncMock(return_value='RA "drop-in" & <b>2026</b>')

    with mock.patch.object(module, "sql_get_public_tournament_name", lookup):
        response = await module.frontend("tournaments/51/results")

    assert isinstance(response, HTMLResponse)
    lookup.assert_awaited_once_with(51)
    body = response.body.decode()
    escaped = "RA &quot;drop-in&quot; &amp; &lt;b&gt;2026&lt;/b&gt;"
    assert f"<title>{escaped}</title>" in body
    assert f'<meta property="og:title" content="{escaped}" />' in body


async def test_frontend_does_not_name_a_non_public_tournament(frontend_dist, monkeypatch) -> None:
    monkeypatch.setattr(config_module.config, "serve_frontend", True)
    monkeypatch.setattr(config_module.config, "api_prefix", "/api")
    _patch_router_prefixes(monkeypatch, "/api")

    module = _load_fresh_app("bracket._app_frontend_probe_private")
    lookup = mock.AsyncMock(return_value=None)

    with mock.patch.object(module, "sql_get_public_tournament_name", lookup):
        response = await module.frontend("tournaments/51/results")

    assert isinstance(response, FileResponse)
    assert str(response.path).endswith(os.path.join("frontend-dist", "index.html"))


async def test_frontend_block_requires_api_prefix(frontend_dist, monkeypatch) -> None:
    monkeypatch.setattr(config_module.config, "serve_frontend", True)
    monkeypatch.setattr(config_module.config, "api_prefix", "")  # invalid: must start with "/"

    with pytest.raises(AssertionError, match="API_PREFIX"):
        _load_fresh_app("bracket._app_frontend_probe_badprefix")


async def _run_lifespan(module) -> None:
    async with module.lifespan(None):
        pass


async def test_lifespan_production_runs_migrations_cronjobs_and_cors_warning() -> None:
    module = _load_fresh_app("bracket._app_lifespan_probe_prod")

    mock_db = mock.AsyncMock()
    mock_db.fetch_val = mock.AsyncMock(return_value=5)  # table_count > 1
    mock_config = mock.Mock(auto_run_migrations=True)
    mock_config.is_cors_enabled.return_value = False

    with (
        mock.patch.object(module, "environment", Environment.PRODUCTION),
        mock.patch.object(module, "config", mock_config),
        mock.patch.object(module, "database", mock_db),
        mock.patch.object(module, "alembic_run_migrations") as mock_migrate,
        mock.patch.object(module, "init_db_when_empty", new=mock.AsyncMock()),
        mock.patch.object(module, "start_cronjobs") as mock_cronjobs,
        mock.patch.object(module, "logger") as mock_logger,
        mock.patch.object(module.AsyncioTasksManager, "gather", new=mock.AsyncMock()),
    ):
        await _run_lifespan(module)

    mock_migrate.assert_called_once()  # line 60
    mock_cronjobs.assert_called_once()  # line 65
    mock_logger.warning.assert_called_once()  # line 68
    mock_db.disconnect.assert_awaited_once()  # line 73 (non-CI)


async def test_lifespan_production_skips_migration_when_table_count_low() -> None:
    module = _load_fresh_app("bracket._app_lifespan_probe_prod_empty")

    mock_db = mock.AsyncMock()
    mock_db.fetch_val = mock.AsyncMock(return_value=1)  # table_count not > 1
    mock_config = mock.Mock(auto_run_migrations=True)
    mock_config.is_cors_enabled.return_value = True  # no cors warning

    with (
        mock.patch.object(module, "environment", Environment.PRODUCTION),
        mock.patch.object(module, "config", mock_config),
        mock.patch.object(module, "database", mock_db),
        mock.patch.object(module, "alembic_run_migrations") as mock_migrate,
        mock.patch.object(module, "init_db_when_empty", new=mock.AsyncMock()),
        mock.patch.object(module, "start_cronjobs") as mock_cronjobs,
        mock.patch.object(module.AsyncioTasksManager, "gather", new=mock.AsyncMock()),
    ):
        await _run_lifespan(module)

    mock_migrate.assert_not_called()
    # Cronjobs still start (PRODUCTION), but no cors warning since cors is enabled.
    mock_cronjobs.assert_called_once()


async def test_lifespan_ci_skips_migration_and_disconnect() -> None:
    module = _load_fresh_app("bracket._app_lifespan_probe_ci")

    mock_db = mock.AsyncMock()
    mock_config = mock.Mock(auto_run_migrations=True)

    with (
        mock.patch.object(module, "environment", Environment.CI),
        mock.patch.object(module, "config", mock_config),
        mock.patch.object(module, "database", mock_db),
        mock.patch.object(module, "alembic_run_migrations") as mock_migrate,
        mock.patch.object(module, "init_db_when_empty", new=mock.AsyncMock()),
        mock.patch.object(module, "start_cronjobs") as mock_cronjobs,
        mock.patch.object(module.AsyncioTasksManager, "gather", new=mock.AsyncMock()),
    ):
        await _run_lifespan(module)

    # CI: migrations gated off, cronjobs not started, DB not disconnected (line 72 false).
    mock_migrate.assert_not_called()
    mock_cronjobs.assert_not_called()
    mock_db.disconnect.assert_not_called()
    mock_db.fetch_val.assert_not_called()
