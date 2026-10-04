from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from heliclockter import datetime_utc
from starlette import status

from bracket.config import config
from bracket.logic.subscriptions import setup_demo_account
from bracket.models.db.account import UserAccountType
from bracket.models.db.club import ClubCreateBody
from bracket.models.db.user import (
    DemoUserToRegister,
    UserInsertable,
    UserPasswordToUpdate,
    UserPublic,
    UserToRegister,
    UserToUpdate,
)
from bracket.routes.auth import (
    Token,
    create_access_token_for_user,
    user_authenticated,
    user_authenticated_admin,
)
from bracket.routes.models import (
    AdminUserListResponse,
    SuccessResponse,
    TokenResponse,
    UserPublicResponse,
)
from bracket.sql.clubs import create_club
from bracket.sql.participants import sync_user_team_names
from bracket.sql.users import (
    check_whether_email_is_in_use,
    check_whether_name_is_in_use,
    create_user,
    get_all_users_with_ratings,
    get_user_by_id,
    normalize_email,
    update_user,
    update_user_password,
)
from bracket.utils.i18n import tr
from bracket.utils.id_types import UserId
from bracket.utils.security import hash_password, verify_captcha_token
from bracket.utils.types import assert_some

router = APIRouter(prefix=config.api_prefix)


@router.get("/users", response_model=AdminUserListResponse)
async def list_users(
    _: UserPublic = Depends(user_authenticated_admin),
) -> AdminUserListResponse:
    """Admin-only: all (non-demo) users with their ACTIVE per-category ratings,
    without emails."""
    return AdminUserListResponse(data=await get_all_users_with_ratings())


@router.get("/users/me", response_model=UserPublicResponse)
async def get_user(user_public: UserPublic = Depends(user_authenticated)) -> UserPublicResponse:
    return UserPublicResponse(data=user_public)


@router.get("/users/{user_id}", response_model=UserPublicResponse)
async def get_me(
    user_id: UserId, user_public: UserPublic = Depends(user_authenticated)
) -> UserPublicResponse:
    if user_public.id != user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, tr("无权查看该用户信息"))

    return UserPublicResponse(data=user_public)


@router.put("/users/{user_id}", response_model=UserPublicResponse)
async def update_user_details(
    user_id: UserId,
    user_to_update: UserToUpdate,
    user_public: UserPublic = Depends(user_authenticated),
) -> UserPublicResponse:
    if user_public.id != user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, tr("无权修改该用户信息"))

    _validate_name(user_to_update.name)
    user_to_update.name = user_to_update.name.strip()
    if await check_whether_name_is_in_use(user_to_update.name, exclude_user_id=user_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, tr("该名称已被使用"))
    if normalize_email(user_to_update.email) != (
        user_public.email or None
    ) and await check_whether_email_is_in_use(user_to_update.email):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, tr("该邮箱已被使用"))

    await update_user(user_public.id, user_to_update)
    # Individual-tournament teams carry the participant's name — keep them in
    # sync on rename (settled tournaments keep their historical names).
    if user_to_update.name != user_public.name:
        await sync_user_team_names(user_id, user_to_update.name)
    user_updated = await get_user_by_id(user_id)
    return UserPublicResponse(data=assert_some(user_updated))


@router.put("/users/{user_id}/password", response_model=SuccessResponse)
async def put_user_password(
    user_id: UserId,
    user_to_update: UserPasswordToUpdate,
    user_public: UserPublic = Depends(user_authenticated),
) -> SuccessResponse:
    if user_public.id != user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, tr("无权修改该用户信息"))
    await update_user_password(user_public.id, hash_password(user_to_update.password))
    return SuccessResponse()


def _validate_name(name: str) -> None:
    """The user name is the primary login identifier: required, and it must not
    look like an email address so name-vs-email login resolution stays
    unambiguous. Any other characters (Chinese included) are fine."""
    if name.strip() == "":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, tr("名称不能为空"))
    if "@" in name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, tr("名称不能包含 @ 字符"))


@router.post("/users/register", response_model=TokenResponse)
async def register_user(user_to_register: UserToRegister) -> TokenResponse:
    if not config.allow_user_registration:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, tr("当前暂不开放注册"))

    if not await verify_captcha_token(user_to_register.captcha_token):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, tr("人机验证失败"))

    _validate_name(user_to_register.name)
    user = UserInsertable(
        # Optional — accounts may be registered with just a (unique) name.
        email=user_to_register.email,
        password_hash=hash_password(user_to_register.password),
        name=user_to_register.name.strip(),
        created=datetime_utc.now(),
        account_type=UserAccountType.REGULAR,
    )
    if await check_whether_email_is_in_use(user.email):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, tr("该邮箱已被使用"))
    if await check_whether_name_is_in_use(user.name):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, tr("该名称已被使用"))

    user_created = await create_user(user)
    # Every account gets an implicit personal club so it can organise tournaments
    # immediately; clubs are the (hidden) ownership/permission unit, never chosen
    # by the user.
    await create_club(ClubCreateBody(name=user_created.name), user_created.id)
    access_token = await create_access_token_for_user(user_created.id)
    return TokenResponse(
        data=Token(access_token=access_token, token_type="bearer", user_id=user_created.id)
    )


@router.post("/users/register_demo", response_model=TokenResponse)
async def register_demo_user(user_to_register: DemoUserToRegister) -> TokenResponse:
    if not config.allow_demo_user_registration:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, tr("当前暂不开放演示账户"))

    if not await verify_captcha_token(user_to_register.captcha_token):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, tr("人机验证失败"))

    username = f"demo-{uuid4()}"
    user = UserInsertable(
        email=f"{username}@example.org",
        password_hash=hash_password(str(uuid4())),
        name=username,
        created=datetime_utc.now(),
        account_type=UserAccountType.DEMO,
    )
    if await check_whether_email_is_in_use(user.email):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, tr("该邮箱已被使用"))

    user_created = await create_user(user)
    access_token = await create_access_token_for_user(user_created.id)
    await setup_demo_account(user_created.id)
    return TokenResponse(
        data=Token(access_token=access_token, token_type="bearer", user_id=user_created.id)
    )
