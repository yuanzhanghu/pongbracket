import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest

from bracket.database import database
from bracket.models.db.rating import (
    PROTECTED_RATING_CATEGORY_KEY,
    display_rating_category_name,
)
from bracket.utils.http import HTTPMethod
from bracket.utils.i18n import (
    DEFAULT_LANGUAGE,
    ENTITY_NOUNS,
    INDIVIDUAL_MESSAGES,
    SEEDED_RATING_CATEGORY_NAME,
    SUPPORTED_LANGUAGES,
    TRANSLATIONS,
    parse_accept_language,
    set_language,
    tr,
    tr_entity,
)
from bracket.utils.types import JsonDict
from tests.integration_tests.api.route_gaps_test import rated_individual_tournament
from tests.integration_tests.api.shared import send_request
from tests.integration_tests.mocks import get_mock_token
from tests.integration_tests.models import AuthContext

BAD_CREDENTIALS = {"username": "nobody@example.org", "password": "wrong"}


async def login_error_detail(accept_language: str | None) -> str:
    headers = {} if accept_language is None else {"Accept-Language": accept_language}
    response = JsonDict(
        await send_request(HTTPMethod.POST, "token", BAD_CREDENTIALS, headers=headers)
    )
    return str(response["detail"])


def with_language(headers: dict[str, str], accept_language: str | None) -> dict[str, str]:
    if accept_language is None:
        return headers
    return {**headers, "Accept-Language": accept_language}


@pytest.mark.asyncio(loop_scope="session")
async def test_error_detail_defaults_to_chinese(startup_and_shutdown_uvicorn_server: None) -> None:
    assert await login_error_detail(None) == "邮箱/名称或密码错误"


@pytest.mark.asyncio(loop_scope="session")
async def test_error_detail_follows_accept_language(
    startup_and_shutdown_uvicorn_server: None,
) -> None:
    assert await login_error_detail("en-US,en;q=0.9") == "Incorrect email/username or password"
    assert await login_error_detail("fr") == (
        "Adresse e-mail/nom d'utilisateur ou mot de passe incorrect"
    )
    # Unsupported languages fall back to the default.
    assert await login_error_detail("de-DE,de") == "邮箱/名称或密码错误"


@pytest.mark.asyncio(loop_scope="session")
async def test_language_does_not_leak_between_requests(
    startup_and_shutdown_uvicorn_server: None,
) -> None:
    assert await login_error_detail("en") == "Incorrect email/username or password"
    assert await login_error_detail(None) == "邮箱/名称或密码错误"


def test_parse_accept_language() -> None:
    assert parse_accept_language(None) == DEFAULT_LANGUAGE
    assert parse_accept_language("") == DEFAULT_LANGUAGE
    assert parse_accept_language("*") == DEFAULT_LANGUAGE
    assert parse_accept_language("en-US,en;q=0.9") == "en"
    assert parse_accept_language("fr-CA") == "fr"
    assert parse_accept_language("de,fr;q=0.8,en;q=0.9") == "en"
    assert parse_accept_language("en;q=0") == DEFAULT_LANGUAGE
    assert parse_accept_language("en;q=bogus") == DEFAULT_LANGUAGE


def test_untranslated_message_stays_chinese() -> None:
    assert tr("这条消息没有翻译") == "这条消息没有翻译"


def test_every_message_is_translated_into_every_language() -> None:
    other_languages = set(SUPPORTED_LANGUAGES) - {DEFAULT_LANGUAGE}
    for message, translations in TRANSLATIONS.items():
        assert set(translations) == other_languages, message


def test_every_entity_noun_is_a_translated_message() -> None:
    """The nouns spliced into “找不到 ID 为 {value} 的{name}” are message ids themselves."""
    for class_name, noun in ENTITY_NOUNS.items():
        assert tr_entity(class_name) == noun
        assert noun in TRANSLATIONS, class_name


def test_tr_entity_falls_back_to_the_class_name() -> None:
    assert tr_entity("SomeNewEntity") == "SomeNewEntity"


def test_every_individual_message_is_a_translated_message() -> None:
    """Both sides of the swap are message ids, so both need a catalog entry."""
    for message, individual_message in INDIVIDUAL_MESSAGES.items():
        assert message in TRANSLATIONS, message
        assert individual_message in TRANSLATIONS, individual_message


def test_individual_messages_keep_their_placeholders() -> None:
    """The swapped id is `.format`ted by the same call site as the original."""
    placeholders = re.compile(r"{[a-z_]+}")
    for message, individual_message in INDIVIDUAL_MESSAGES.items():
        assert set(placeholders.findall(message)) == set(
            placeholders.findall(individual_message)
        ), message


@pytest.mark.asyncio(loop_scope="session")
async def test_foreign_key_error_localises_the_entity_noun(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """A bad `StageItemId` used to render as “找不到 ID 为 -1 的 StageItem”."""

    async def detail(accept_language: str | None) -> str:
        response = JsonDict(
            await send_request(
                HTTPMethod.POST,
                f"tournaments/{auth_context.tournament.id}/rounds",
                json={"stage_item_id": -1},
                headers=with_language(auth_context.headers, accept_language),
            )
        )
        return str(response["detail"])

    assert await detail(None) == "找不到 ID 为 -1 的阶段项目"
    assert await detail("en-US,en;q=0.9") == "No stage item found with ID -1"
    assert await detail("fr") == "Impossible de trouver l'élément d'étape avec l'identifiant -1"


@pytest.mark.asyncio(loop_scope="session")
async def test_rated_individual_team_error_is_localised(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """This message used to be English for everyone, regardless of Accept-Language."""

    async def detail(tournament_id: int, accept_language: str | None) -> str:
        response = JsonDict(
            await send_request(
                HTTPMethod.POST,
                f"tournaments/{tournament_id}/teams",
                json={"name": "Free Text Team", "active": True, "player_names": []},
                headers=with_language(auth_context.headers, accept_language),
            )
        )
        return str(response["detail"])

    async with rated_individual_tournament(auth_context.club.id, endpoint="i18n_freetext") as ids:
        tournament_id = ids["tournament"]
        # An individual tournament has participants, not teams, so the message says so.
        assert await detail(tournament_id, None) == (
            "个人积分赛只能通过选择已注册账号来添加参赛者（报名申请或直接添加），不能手动输入名称"
        )
        assert await detail(tournament_id, "en") == (
            "Rated individual tournaments add participants by selecting a registered account "
            "(join request or direct add), not by typing a name"
        )
        assert await detail(tournament_id, "fr") == (
            "Dans un tournoi individuel classé, les participants sont ajoutés en sélectionnant "
            "un compte enregistré (demande d'inscription ou ajout direct), et non en saisissant "
            "un nom"
        )


async def team_not_found_detail(
    tournament_id: int, headers: dict[str, str], accept_language: str | None
) -> str:
    response = JsonDict(
        await send_request(
            HTTPMethod.PUT,
            f"tournaments/{tournament_id}/teams/-1",
            json={"name": "Whoever", "active": True, "player_names": []},
            headers=with_language(headers, accept_language),
        )
    )
    return str(response["detail"])


@pytest.mark.asyncio(loop_scope="session")
async def test_individual_tournament_says_participant_instead_of_team(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """A “team” in an individual tournament is one person, so it is called a participant."""
    async with rated_individual_tournament(
        auth_context.club.id, endpoint="i18n_participant"
    ) as ids:
        tournament_id = ids["tournament"]
        assert await team_not_found_detail(tournament_id, auth_context.headers, None) == (
            "找不到 ID 为 -1 的参赛人员"
        )
        assert await team_not_found_detail(tournament_id, auth_context.headers, "en") == (
            "No participant found with ID -1"
        )
        assert await team_not_found_detail(tournament_id, auth_context.headers, "fr") == (
            "Aucun participant trouvé avec l'identifiant -1"
        )


@pytest.mark.asyncio(loop_scope="session")
async def test_team_tournament_keeps_the_team_wording(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """The participant wording is for individual tournaments only; teams stay teams."""
    tournament_id = auth_context.tournament.id
    assert not auth_context.tournament.is_individual
    assert await team_not_found_detail(tournament_id, auth_context.headers, None) == (
        "找不到 ID 为 -1 的队伍"
    )
    assert await team_not_found_detail(tournament_id, auth_context.headers, "en") == (
        "No team found with ID -1"
    )
    assert await team_not_found_detail(tournament_id, auth_context.headers, "fr") == (
        "Aucune équipe trouvée avec l'identifiant -1"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_untrusted_direct_add_error_is_localised(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """The detail is passed positionally here, which is how it escaped the first sweep."""

    async def detail(tournament_id: int, accept_language: str | None) -> str:
        response = JsonDict(
            await send_request(
                HTTPMethod.POST,
                f"tournaments/{tournament_id}/participants",
                json={"user_id": -1},
                headers=with_language(auth_context.headers, accept_language),
            )
        )
        return str(response["detail"])

    async with rated_individual_tournament(auth_context.club.id, endpoint="i18n_untrusted") as ids:
        tournament_id = ids["tournament"]
        assert await detail(tournament_id, None) == "该账号未授权你直接将其加入比赛"
        assert await detail(tournament_id, "en") == (
            "This account has not authorised you to add them directly"
        )
        assert await detail(tournament_id, "fr") == (
            "Ce compte ne vous a pas autorisé à l'inscrire directement"
        )


# --- The built-in rating category's name: a DB row, not a message ---


@asynccontextmanager
async def seeded_rating_category() -> AsyncIterator[int]:
    """The built-in category exactly as DB init seeds it.

    The test schema is created from the SQLAlchemy metadata, which carries no seed rows,
    so it is inserted here. A row another suite left behind is reused and restored
    afterwards instead of fought over — `key` is unique.
    """
    existing = await database.fetch_one(
        "SELECT id, name FROM rating_categories WHERE key = :k",
        {"k": PROTECTED_RATING_CATEGORY_KEY},
    )
    if existing is None:
        category_id = await database.fetch_val(
            "INSERT INTO rating_categories (key, name, algorithm) "
            "VALUES (:k, :n, 'chinatt') RETURNING id",
            {"k": PROTECTED_RATING_CATEGORY_KEY, "n": SEEDED_RATING_CATEGORY_NAME},
        )
    else:
        category_id = existing["id"]
        await database.execute(
            "UPDATE rating_categories SET name = :n WHERE id = :i",
            {"n": SEEDED_RATING_CATEGORY_NAME, "i": category_id},
        )
    try:
        yield int(category_id)
    finally:
        if existing is None:
            await database.execute(
                "DELETE FROM rating_categories WHERE id = :i", {"i": category_id}
            )
        else:
            await database.execute(
                "UPDATE rating_categories SET name = :n WHERE id = :i",
                {"n": existing["name"], "i": category_id},
            )


@asynccontextmanager
async def site_admin_headers() -> AsyncIterator[dict[str, str]]:
    """A throwaway site admin: renaming a rating category is an admin-only action."""
    email = f"i18n_admin_{uuid4()}@test"
    admin_id = await database.fetch_val(
        "INSERT INTO users (email, name, password_hash, account_type, is_admin) "
        "VALUES (:e, 'I18nAdmin', 'x', 'REGULAR', true) RETURNING id",
        {"e": email},
    )
    try:
        yield {"Authorization": f"Bearer {get_mock_token(email)}"}
    finally:
        await database.execute("DELETE FROM users WHERE id = :i", {"i": admin_id})


async def listed_category_name(
    category_id: int, headers: dict[str, str], accept_language: str | None
) -> str:
    response = JsonDict(
        await send_request(
            HTTPMethod.GET, "rating-categories", headers=with_language(headers, accept_language)
        )
    )
    (category,) = [c for c in response["data"] if c["id"] == category_id]
    return str(category["name"])


@pytest.mark.asyncio(loop_scope="session")
async def test_builtin_rating_category_name_is_localised(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """The seeded name lives in a table, so it used to stay Chinese in every language."""
    async with seeded_rating_category() as category_id:
        headers = auth_context.headers
        assert await listed_category_name(category_id, headers, None) == "加华积分"
        assert await listed_category_name(category_id, headers, "en-US,en;q=0.9") == "Jiahua Rating"
        assert await listed_category_name(category_id, headers, "fr") == "Cote Jiahua"
        # Unsupported languages fall back to the default, like every other string.
        assert await listed_category_name(category_id, headers, "de-DE,de") == "加华积分"


@pytest.mark.asyncio(loop_scope="session")
async def test_my_ratings_localises_the_builtin_category_name(
    startup_and_shutdown_uvicorn_server: None,
) -> None:
    """`/me/ratings` selects the name under an alias of its own — a second read path."""

    async def category_name(headers: dict[str, str], accept_language: str | None) -> str:
        response = JsonDict(
            await send_request(
                HTTPMethod.GET, "me/ratings", headers=with_language(headers, accept_language)
            )
        )
        return str(response["data"][0]["category_name"])

    async with seeded_rating_category() as category_id:
        email = f"i18n_rated_{uuid4()}@test"
        user_id = await database.fetch_val(
            "INSERT INTO users (email, name, password_hash, account_type) "
            "VALUES (:e, 'I18nRated', 'x', 'REGULAR') RETURNING id",
            {"e": email},
        )
        await database.execute(
            """
            INSERT INTO player_ratings
                (category_id, user_id, initial_rating, current_rating, status, last_updated)
            VALUES (:c, :u, 1500, 1500, 'ACTIVE', NOW())
            """,
            {"c": category_id, "u": user_id},
        )
        headers = {"Authorization": f"Bearer {get_mock_token(email)}"}
        try:
            assert await category_name(headers, None) == "加华积分"
            assert await category_name(headers, "en") == "Jiahua Rating"
            assert await category_name(headers, "fr") == "Cote Jiahua"
        finally:
            await database.execute("DELETE FROM player_ratings WHERE user_id = :u", {"u": user_id})
            await database.execute("DELETE FROM users WHERE id = :i", {"i": user_id})


@pytest.mark.asyncio(loop_scope="session")
async def test_settlement_review_queue_localises_the_builtin_category_name(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """The third read path, and the only one whose response carries no category key:
    the queue lists every requested, unsettled tournament and joins the name in."""

    async def category_name(
        tournament_id: int, headers: dict[str, str], accept_language: str | None
    ) -> str:
        response = JsonDict(
            await send_request(
                HTTPMethod.GET,
                "admin/settlement-reviews",
                headers=with_language(headers, accept_language),
            )
        )
        (item,) = [i for i in response["data"] if i["tournament_id"] == tournament_id]
        return str(item["category_name"])

    async with seeded_rating_category() as category_id, site_admin_headers() as admin:
        tournament_id = await database.fetch_val(
            """
            INSERT INTO tournaments
                (name, start_time, club_id, dashboard_public, is_individual,
                 rating_category_id, settlement_requested_at)
            VALUES ('I18n Review', NOW(), :club, true, true, :cat, NOW())
            RETURNING id
            """,
            {"club": auth_context.club.id, "cat": category_id},
        )
        try:
            assert await category_name(tournament_id, admin, None) == "加华积分"
            assert await category_name(tournament_id, admin, "en") == "Jiahua Rating"
            assert await category_name(tournament_id, admin, "fr") == "Cote Jiahua"
        finally:
            await database.execute("DELETE FROM tournaments WHERE id = :i", {"i": tournament_id})


@pytest.mark.asyncio(loop_scope="session")
async def test_renamed_rating_category_is_shown_verbatim_in_every_language(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """The safety net: an admin who renames the built-in category owns its name from
    then on, in every language. Only the untouched seed is ever translated."""
    async with seeded_rating_category() as category_id, site_admin_headers() as admin:

        async def rename(name: str) -> str:
            response = JsonDict(
                await send_request(
                    HTTPMethod.PUT,
                    f"rating-categories/{category_id}",
                    json={"name": name, "algorithm": "chinatt"},
                    headers=with_language(admin, "en"),
                )
            )
            return str(response["data"]["name"])

        renamed = "Ligue interne"
        assert await rename(renamed) == renamed
        for language in (None, "en", "fr"):
            assert (
                await listed_category_name(category_id, auth_context.headers, language) == renamed
            )
        # The stored name is what decides, not a one-way flag: put the seed back and the
        # translation resumes.
        assert await rename(SEEDED_RATING_CATEGORY_NAME) == "Jiahua Rating"
        assert await listed_category_name(category_id, auth_context.headers, "fr") == "Cote Jiahua"


def test_only_the_untouched_seed_of_the_builtin_category_is_translated() -> None:
    """Both halves of the guard: the protected key and the seeded name."""
    set_language("en")
    try:
        assert (
            display_rating_category_name(PROTECTED_RATING_CATEGORY_KEY, SEEDED_RATING_CATEGORY_NAME)
            == "Jiahua Rating"
        )
        # An admin's own name, even if it is Chinese.
        assert display_rating_category_name(PROTECTED_RATING_CATEGORY_KEY, "内部联赛") == "内部联赛"
        # Another category that happens to carry the same name is not the built-in one.
        assert (
            display_rating_category_name("SomeOtherKey", SEEDED_RATING_CATEGORY_NAME)
            == SEEDED_RATING_CATEGORY_NAME
        )
    finally:
        set_language(DEFAULT_LANGUAGE)
