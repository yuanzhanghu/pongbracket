"""Extra coverage for bracket.utils.db_init branches that don't run under CI:

- create_admin_user (100-112)
- init_db_when_empty's "empty DB" create-tables/create-admin branch (123-128)
- sql_create_dev_db's `if real_user_id is not None` binding of the real admin (180)

These only fire when the environment is treated as DEVELOPMENT and the admin user is
absent, so we patch the module-level `environment` accordingly and clean up after.
"""

from unittest import mock

import pytest

import bracket.utils.db_init as db_init_module
from bracket.config import Environment, config
from bracket.database import database
from bracket.schema import users
from bracket.sql.users import delete_user_and_owned_clubs, get_user
from bracket.utils.db_init import create_admin_user, init_db_when_empty, sql_create_dev_db


async def _delete_user_by_email(email: str) -> None:
    user = await get_user(email)
    if user is not None:
        await database.execute(users.delete().where(users.c.id == user.id))


@pytest.mark.asyncio(loop_scope="session")
async def test_create_admin_user_and_empty_db_branch(reinit_database) -> None:
    """init_db_when_empty creates tables + admin when the DB looks empty under
    DEVELOPMENT and the admin user is absent. (db_init.py 100-112, 123-128)"""
    assert config.admin_email
    # Make sure no stale admin row exists from a prior run.
    await _delete_user_by_email(config.admin_email)

    created_user_id = None
    try:
        with mock.patch.object(db_init_module, "environment", Environment.DEVELOPMENT):
            # DEVELOPMENT + admin user missing -> takes the create branch.
            created_user_id = await init_db_when_empty()

        assert created_user_id is not None
        admin = await get_user(config.admin_email)
        assert admin is not None
        assert admin.id == created_user_id
    finally:
        if created_user_id is not None:
            await delete_user_and_owned_clubs(created_user_id)
        await _delete_user_by_email(config.admin_email)


@pytest.mark.asyncio(loop_scope="session")
async def test_create_admin_user_directly(reinit_database) -> None:
    """create_admin_user inserts the configured admin. (db_init.py 100-112)"""
    assert config.admin_email
    await _delete_user_by_email(config.admin_email)

    admin_id = None
    try:
        admin_id = await create_admin_user()
        admin = await get_user(config.admin_email)
        assert admin is not None and admin.id == admin_id
    finally:
        if admin_id is not None:
            await database.execute(users.delete().where(users.c.id == admin_id))


@pytest.mark.asyncio(loop_scope="session")
async def test_sql_create_dev_db_binds_real_admin(reinit_database) -> None:
    """Under DEVELOPMENT, init_db_when_empty returns the real admin id, so
    sql_create_dev_db binds it to the dummy club. (db_init.py 180)

    DUMMY_USER's email is hardcoded to the CI admin email ("admin@example.com"), so the
    admin email is overridden to a unique value to avoid the dummy-user insert colliding
    with the freshly created admin.
    """
    unique_admin_email = "dev_admin_probe@example.com"
    await _delete_user_by_email(unique_admin_email)

    dummy_user_id = None
    try:
        with (
            mock.patch.object(db_init_module, "environment", Environment.DEVELOPMENT),
            mock.patch.object(config, "admin_email", unique_admin_email),
        ):
            dummy_user_id = await sql_create_dev_db()

            # The real admin was created and bound (line 180 path ran).
            admin = await get_user(unique_admin_email)
            assert admin is not None
            binding = await database.fetch_val(
                "SELECT COUNT(*) FROM users_x_clubs WHERE user_id = :u", {"u": admin.id}
            )
            assert binding >= 1
    finally:
        # sql_create_dev_db rebuilds the whole schema with dummy data; remove the rows we
        # can attribute to this test (dummy owner + the created admin).
        if dummy_user_id is not None:
            await delete_user_and_owned_clubs(dummy_user_id)
        await _delete_user_by_email(unique_admin_email)
