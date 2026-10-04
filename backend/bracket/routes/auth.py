from typing import Any

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from heliclockter import datetime_utc, timedelta
from jwt import DecodeError, ExpiredSignatureError
from pydantic import BaseModel
from starlette.requests import Request

from bracket.config import config
from bracket.database import database
from bracket.models.db.tournament import Tournament
from bracket.models.db.user import UserInDB, UserPublic
from bracket.schema import tournaments
from bracket.sql.participants import is_bound_in_tournament, is_tournament_scorer
from bracket.sql.tournaments import sql_get_tournament_by_endpoint_name
from bracket.sql.users import (
    get_user,
    get_user_access_to_club,
    get_user_access_to_tournament,
    get_user_by_id,
    get_user_by_login,
    get_user_token_version,
)
from bracket.utils.db import fetch_all_parsed
from bracket.utils.i18n import tr
from bracket.utils.id_types import ClubId, TournamentId, UserId
from bracket.utils.security import verify_password
from bracket.utils.types import assert_some

router = APIRouter(prefix=config.api_prefix)

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 365 * 24 * 60  # 1 year

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


# def convert_openid(response: dict[str, Any]) -> OpenID:
#     """Convert user information returned by OIDC"""
#     return OpenID(display_name=response["sub"])


# os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

# sso = GoogleSSO(
#     client_id="test",
#     client_secret="secret",
#     redirect_uri="http://localhost:8080/sso_callback",
#     allow_insecure_http=config.allow_insecure_http_sso,
# )


class Token(BaseModel):
    access_token: str
    token_type: str
    user_id: UserId


class TokenData(BaseModel):
    email: str | None = None


async def authenticate_user(login: str, password: str) -> UserInDB | None:
    # The login identifier may be an email address or a (unique) user name —
    # Chinese names included.
    user = await get_user_by_login(login)

    if not user or not verify_password(password, user.password_hash):
        return None

    return user


def create_access_token(data: dict[str, Any], expires_delta: timedelta) -> str:
    to_encode = data.copy()
    expire = datetime_utc.now() + expires_delta
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, config.jwt_secret, algorithm=ALGORITHM)


async def create_access_token_for_user(user_id: UserId) -> str:
    """Stamps the token with the user's current generation (`tv`), so a later
    password change can retire it."""
    return create_access_token(
        data={"user": str(user_id), "tv": await get_user_token_version(user_id)},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )


async def check_jwt_and_get_user(token: str) -> UserPublic | None:
    try:
        payload = jwt.decode(token, config.jwt_secret, algorithms=[ALGORITHM])
        subject = payload.get("user")
        if subject is None:
            return None
    except (DecodeError, ExpiredSignatureError):
        return None

    subject = str(subject)
    # New tokens carry the user id (emails are optional now); tokens issued
    # before the switch carry the email — keep honouring them until they expire.
    if subject.isdigit():
        user_public = await get_user_by_id(UserId(int(subject)))
    else:
        user = await get_user(email=subject)
        user_public = UserPublic.model_validate(user.model_dump()) if user is not None else None

    if user_public is None:
        return None

    # A password change bumps the generation, retiring every token signed under an
    # older one. Tokens predating the claim read as generation 0, which is where
    # every account starts, so introducing this logs nobody out.
    if int(payload.get("tv", 0)) != await get_user_token_version(user_public.id):
        return None

    return user_public


async def user_authenticated(token: str = Depends(oauth2_scheme)) -> UserPublic:
    user = await check_jwt_and_get_user(token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=tr("登录状态无效，请重新登录"),
            headers={"WWW-Authenticate": "Bearer"},
        )

    return UserPublic.model_validate(user.model_dump())


async def user_authenticated_for_tournament(
    tournament_id: TournamentId, token: str = Depends(oauth2_scheme)
) -> UserPublic:
    user = await check_jwt_and_get_user(token)

    if not user or not await get_user_access_to_tournament(tournament_id, user.id):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=tr("登录状态无效，请重新登录"),
            headers={"WWW-Authenticate": "Bearer"},
        )

    return UserPublic.model_validate(user.model_dump())


async def user_authenticated_admin(token: str = Depends(oauth2_scheme)) -> UserPublic:
    user = await check_jwt_and_get_user(token)
    if not user or not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=tr("该操作需要站点管理员权限"),
            headers={"WWW-Authenticate": "Bearer"},
        )

    return UserPublic.model_validate(user.model_dump())


async def user_can_record_results(
    tournament_id: TournamentId, token: str = Depends(oauth2_scheme)
) -> UserPublic:
    """Club members OR explicitly-authorised tournament scorers may write scores."""
    from bracket.sql.participants import is_tournament_scorer

    user = await check_jwt_and_get_user(token)
    if user is not None and (
        await get_user_access_to_tournament(tournament_id, user.id)
        or await is_tournament_scorer(tournament_id, user.id)
    ):
        return UserPublic.model_validate(user.model_dump())

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=tr("你没有权限为本比赛录入比分"),
        headers={"WWW-Authenticate": "Bearer"},
    )


async def user_authenticated_for_club(
    club_id: ClubId, token: str = Depends(oauth2_scheme)
) -> UserPublic:
    user = await check_jwt_and_get_user(token)

    if not user or not await get_user_access_to_club(club_id, user.id):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=tr("登录状态无效，请重新登录"),
            headers={"WWW-Authenticate": "Bearer"},
        )

    return UserPublic.model_validate(user.model_dump())


async def user_authenticated_or_public_dashboard(
    tournament_id: TournamentId, request: Request
) -> UserPublic | None:
    try:
        token: str = assert_some(await oauth2_scheme(request))
        user = await check_jwt_and_get_user(token)
        # Readers of a tournament: club members, plus its scorers and bound
        # participants (so they can view a private tournament they are part of —
        # e.g. a scorer opening the results page to record scores). Site admins may
        # read any tournament (e.g. to inspect matches while reviewing initial
        # ratings) — read-only; managing still requires membership.
        if user is not None and (
            user.is_admin
            or await get_user_access_to_tournament(tournament_id, user.id)
            or await is_tournament_scorer(tournament_id, user.id)
            or await is_bound_in_tournament(tournament_id, user.id)
        ):
            return user
    except HTTPException:
        pass

    tournaments_fetched = await fetch_all_parsed(
        database, Tournament, tournaments.select().where(tournaments.c.id == tournament_id)
    )
    if len(tournaments_fetched) < 1 or not tournaments_fetched[0].dashboard_public:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=tr("登录状态无效，或该页面未公开"),
            headers={"WWW-Authenticate": "Bearer"},
        )

    return None


async def user_authenticated_or_public_dashboard_by_endpoint_name(
    request: Request, endpoint_name: str | None = None
) -> UserPublic | None:
    # When resolving a tournament by its public dashboard endpoint/id, a token is
    # NOT required: anyone (logged out or a logged-in non-member) may view a
    # public dashboard. We read the token off the request manually so a missing
    # token does not auto-401 (unlike Depends(oauth2_scheme)).
    if endpoint_name is not None:
        if await sql_get_tournament_by_endpoint_name(endpoint_name) is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=tr("登录状态无效，请重新登录"),
                headers={"WWW-Authenticate": "Bearer"},
            )
        return None

    # No endpoint_name: this is the authenticated tournament listing, which does
    # require a valid token.
    return await user_authenticated(assert_some(await oauth2_scheme(request)))


@router.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()) -> Token:
    user = await authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=tr("邮箱/名称或密码错误"),
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = await create_access_token_for_user(user.id)
    return Token(access_token=access_token, token_type="bearer", user_id=user.id)


# @router.get("/login", summary='SSO login')
# async def sso_login() -> RedirectResponse:
#     """Generate login url and redirect"""
#     return cast(RedirectResponse, await sso.get_login_redirect())
#
#
# @router.get("/sso_callback", summary='SSO callback')
# async def sso_callback(request: Request) -> dict[str, Any]:
#     """Process login response from OIDC and return user info"""
#     user = await sso.verify_and_process(request)
#     if user is None:
#         raise HTTPException(401, "Failed to fetch user information")
#     return {
#         "id": user.id,
#         "picture": user.picture,
#         "display_name": user.display_name,
#         "email": user.email,
#         "provider": user.provider,
#     }
