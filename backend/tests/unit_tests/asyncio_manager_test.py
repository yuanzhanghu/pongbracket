import asyncio

import pytest

from bracket.utils.asyncio import AsyncioTasksManager


async def test_add_coroutine_registers_task_and_done_callback_discards_it() -> None:
    AsyncioTasksManager._tasks.clear()

    async def noop() -> None:
        return None

    task = AsyncioTasksManager.add_coroutine(noop())
    assert isinstance(task, asyncio.Task)
    assert task in AsyncioTasksManager._tasks

    await task

    assert task not in AsyncioTasksManager._tasks


async def test_gather_cancels_pending_tasks() -> None:
    AsyncioTasksManager._tasks.clear()

    async def pending() -> None:
        await asyncio.sleep(3600)

    tasks = [AsyncioTasksManager.add_coroutine(pending()) for _ in range(3)]
    assert AsyncioTasksManager._tasks == set(tasks)

    await AsyncioTasksManager.gather()

    for task in tasks:
        with pytest.raises(asyncio.CancelledError):
            await task
        assert task.cancelled()

    AsyncioTasksManager._tasks.clear()


async def test_gather_with_no_pending_tasks_does_nothing() -> None:
    AsyncioTasksManager._tasks.clear()
    assert not AsyncioTasksManager._tasks

    result = await AsyncioTasksManager.gather()

    assert result is None
    assert not AsyncioTasksManager._tasks
