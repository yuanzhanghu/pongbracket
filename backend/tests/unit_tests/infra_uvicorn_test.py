"""Unit tests for bracket.uvicorn (ReloaderThread + RestartableUvicornWorker).

No DB or server needed: everything is exercised with mocks. The `while True`
loops in ReloaderThread.run are broken out of by making time.sleep raise a
sentinel exception after the first iteration.
"""

import warnings
from unittest import mock

import pytest

with warnings.catch_warnings():
    # `uvicorn.workers` emits a DeprecationWarning on import, which the project's
    # filterwarnings=error config would otherwise turn into a collection error.
    warnings.simplefilter("ignore", DeprecationWarning)
    import bracket.uvicorn as uvicorn_module
    from bracket.uvicorn import ReloaderThread, RestartableUvicornWorker


class _StopLoop(Exception):
    pass


def test_reloader_thread_kills_when_worker_not_alive() -> None:
    worker = mock.Mock()
    worker.alive = False
    thread = ReloaderThread(worker)

    with (
        mock.patch.object(uvicorn_module.os, "kill") as mock_kill,
        mock.patch.object(uvicorn_module.os, "getpid", return_value=4321),
        mock.patch.object(uvicorn_module.time, "sleep", side_effect=_StopLoop),
    ):
        with pytest.raises(_StopLoop):
            thread.run()

    mock_kill.assert_called_once()
    assert mock_kill.call_args.args[0] == 4321


def test_reloader_thread_does_not_kill_when_worker_alive() -> None:
    worker = mock.Mock()
    worker.alive = True
    thread = ReloaderThread(worker)

    with (
        mock.patch.object(uvicorn_module.os, "kill") as mock_kill,
        mock.patch.object(uvicorn_module.time, "sleep", side_effect=_StopLoop),
    ):
        with pytest.raises(_StopLoop):
            thread.run()

    mock_kill.assert_not_called()


def test_restartable_worker_init_creates_reloader_thread() -> None:
    with mock.patch.object(uvicorn_module.UvicornWorker, "__init__", return_value=None):
        worker = RestartableUvicornWorker()

    assert isinstance(worker._reloader_thread, ReloaderThread)


def test_restartable_worker_run_starts_reloader_when_reload_enabled() -> None:
    with mock.patch.object(uvicorn_module.UvicornWorker, "__init__", return_value=None):
        worker = RestartableUvicornWorker()

    worker.cfg = mock.Mock(reload=True)
    worker._reloader_thread = mock.Mock()

    with mock.patch.object(uvicorn_module.UvicornWorker, "run") as mock_super_run:
        worker.run()

    worker._reloader_thread.start.assert_called_once()
    mock_super_run.assert_called_once()


def test_restartable_worker_run_skips_reloader_when_reload_disabled() -> None:
    with mock.patch.object(uvicorn_module.UvicornWorker, "__init__", return_value=None):
        worker = RestartableUvicornWorker()

    worker.cfg = mock.Mock(reload=False)
    worker._reloader_thread = mock.Mock()

    with mock.patch.object(uvicorn_module.UvicornWorker, "run") as mock_super_run:
        worker.run()

    worker._reloader_thread.start.assert_not_called()
    mock_super_run.assert_called_once()
