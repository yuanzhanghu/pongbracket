import glob
import html
import re
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from starlette.exceptions import HTTPException
from starlette.middleware.base import RequestResponseEndpoint
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import HTMLResponse, JSONResponse, Response
from starlette.staticfiles import StaticFiles

from bracket.config import Environment, config, environment, init_sentry
from bracket.cronjobs.scheduling import start_cronjobs
from bracket.database import database
from bracket.models.metrics import RequestDefinition, get_request_metrics
from bracket.routes import (
    auth,
    clubs,
    courts,
    favorites,
    internals,
    matches,
    participants,
    players,
    rankings,
    ratings,
    rounds,
    showcase,
    stage_item_inputs,
    stage_items,
    stages,
    teams,
    tournaments,
    users,
)
from bracket.sql.tournaments import (
    sql_get_public_tournament_name,
    sql_get_tournament_is_individual,
)
from bracket.utils.alembic import alembic_run_migrations
from bracket.utils.asyncio import AsyncioTasksManager
from bracket.utils.db_init import init_db_when_empty
from bracket.utils.i18n import parse_accept_language, set_individual_wording, set_language
from bracket.utils.id_types import TournamentId
from bracket.utils.logging import logger

init_sentry()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await database.connect()

    # Bring an already-initialised DB up to head BEFORE any ORM query: init_db_when_empty
    # reads `users` through the current schema, which fails if a new column hasn't been
    # migrated in yet. A fresh/empty DB is initialised by init_db_when_empty
    # (create_all + stamp head); running migrations from base on an empty DB would replay
    # the whole chain, so only migrate when the schema already exists.
    if config.auto_run_migrations and environment is not Environment.CI:
        table_count = await database.fetch_val(
            "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'"
        )
        if table_count > 1:
            alembic_run_migrations()

    await init_db_when_empty()

    if environment is Environment.PRODUCTION:
        start_cronjobs()

    if environment is Environment.PRODUCTION and not config.is_cors_enabled():
        logger.warning("It's advised to set the `CORS_ORIGINS` environment variable in production")

    yield

    if environment is not Environment.CI:
        await database.disconnect()

    await AsyncioTasksManager.gather()


routers = {
    "Auth": auth.router,
    "Clubs": clubs.router,
    "Courts": courts.router,
    "Favorites": favorites.router,
    "Internals": internals.router,
    "Matches": matches.router,
    "Participants": participants.router,
    "Players": players.router,
    "Rankings": rankings.router,
    "Ratings": ratings.router,
    "Rounds": rounds.router,
    "Showcase": showcase.router,
    "Stage Items": stage_items.router,
    "Stage Item Inputs": stage_item_inputs.router,
    "Stages": stages.router,
    "Teams": teams.router,
    "Tournaments": tournaments.router,
    "Users": users.router,
}

table_of_contents = "\n\n".join(
    [f"- [{tag}](#tag/{tag.replace(' ', '-')})" for tag in routers.keys()]
)


description = f"""
### Description
This API allows you to do everything the frontend of [Bracket](https://github.com/evroon/bracket)
allows you to do (the frontend uses this API as well).

Fore more information, see the [documentation](https://docs.bracketapp.nl).

### Table of Contents
*(links only work for [ReDoc](https://api.bracketapp.nl/redoc), not for Swagger UI)*

{table_of_contents}

### Links
GitHub: <https://github.com/evroon/bracket>

Docs: <https://docs.bracketapp.nl>

Demo: <https://www.bracketapp.nl/demo>

API docs (Redoc): <https://api.bracketapp.nl/redoc>

API docs (Swagger UI): <https://api.bracketapp.nl/docs>
"""

app = FastAPI(
    title="Bracket API",
    docs_url="/docs",
    version="1.0.0",
    lifespan=lifespan,
    summary="API for Bracket, an open source tournament system.",
    description=description,
    license_info={
        "name": "AGPL-3.0",
        "url": "https://www.gnu.org/licenses/agpl-3.0.en.html",
    },
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins,
    allow_origin_regex=config.cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_process_time_header(request: Request, call_next: RequestResponseEndpoint) -> Response:
    start_time = time.time()
    request_metrics = get_request_metrics()
    request_metrics.request_count[RequestDefinition.from_request(request)] += 1
    response = await call_next(request)
    process_time = time.time() - start_time
    request_metrics.response_time[RequestDefinition.from_request(request)] = process_time
    return response


# Added last, so it is the outermost middleware: the language is bound to the request
# context before any route handler, dependency or exception handler runs. ContextVars are
# per-task and every request runs in its own task, so the value cannot leak between them.
@app.middleware("http")
async def set_request_language(request: Request, call_next: RequestResponseEndpoint) -> Response:
    set_language(parse_accept_language(request.headers.get("accept-language")))
    return await call_next(request)


# Every tournament-scoped route is mounted under this prefix.
TOURNAMENT_PATH_PATTERN = re.compile(r"/tournaments/(\d+)(?:/|$)")


@app.middleware("http")
async def set_request_wording(request: Request, call_next: RequestResponseEndpoint) -> Response:
    """Bind the wording of team-flavoured messages to the tournament being addressed.

    A "team" in an individual tournament is a single person, so its messages say 参赛人员
    (participant) instead of 队伍. Resolved here, once per request, because those messages
    are raised all over the routes, sql and logic layers, most of which never load the
    tournament they belong to.
    """
    match = TOURNAMENT_PATH_PATTERN.search(request.url.path)
    set_individual_wording(
        await sql_get_tournament_is_individual(TournamentId(int(match.group(1))))
        if match is not None
        else False
    )
    return await call_next(request)


@app.exception_handler(HTTPException)
async def validation_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse({"detail": "Internal server error"}, status_code=500)


app.mount(f"{config.api_prefix}/static", StaticFiles(directory="static"), name="static")

for tag, router in routers.items():
    assert router.prefix == config.api_prefix, f"Prefix not set on router with tag `{tag}`"
    app.include_router(router, tags=[tag])

if config.serve_frontend:
    msg = "API_PREFIX env var must be set (e.g. `/api`) when serving the frontend"
    assert config.api_prefix.startswith("/"), msg

    frontend_root = Path("frontend-dist")
    allowed_paths = list(glob.iglob("frontend-dist/**/*", recursive=True))
    index_html = (frontend_root / Path("index.html")).read_text()

    # Chat apps (WeChat, Slack, ...) build their link preview from the HTML they
    # fetch, without running the app's JavaScript, so the shared card would read
    # the placeholder site name for every tournament. These name the tournament in
    # the HTML itself; the browser tab is still titled by `DocumentHead` on mount.
    tournament_path_pattern = re.compile(r"^tournaments/(\d{1,9})(?:/|$)")
    title_tag_pattern = re.compile(r"<title>.*?</title>", re.DOTALL)

    def index_html_titled(name: str) -> str:
        title = html.escape(name)
        tags = f'<title>{title}</title><meta property="og:title" content="{title}" />'
        return title_tag_pattern.sub(lambda _: tags, index_html, count=1)

    @app.get("/{full_path:path}")
    async def frontend(full_path: str) -> Response:
        path = frontend_root / Path(full_path)

        # Checking `str(path) in allowed_paths` should be enough here but we check for more cases
        # to be sure and avoid AI tools raising false positives.
        if (
            path.exists()
            and path.is_file()
            and str(path) in allowed_paths
            and frontend_root in path.parents
        ):
            return FileResponse(path)

        tournament_match = tournament_path_pattern.match(full_path)
        if tournament_match is not None:
            name = await sql_get_public_tournament_name(
                TournamentId(int(tournament_match.group(1)))
            )
            if name is not None:
                return HTMLResponse(index_html_titled(name))

        return FileResponse(frontend_root / Path("index.html"))
