from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.enums import UserRole
from app.core.security import DEFAULT_USER_EMAIL, hash_token, read_session
from app.db import get_session
from app.models import User

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def ensure_default_user(session: AsyncSession) -> User:
    user = (await session.execute(select(User).where(User.email == DEFAULT_USER_EMAIL))).scalar_one_or_none()
    if user is None:
        user = User(email=DEFAULT_USER_EMAIL, name="Default user", role=UserRole.ADMIN.value)
        session.add(user)
        await session.commit()
    return user


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": "not_authenticated", "message": "Sign in required."},
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(request: Request, session: SessionDep) -> User:
    settings = get_settings()
    if settings.auth_mode == "none":
        return await ensure_default_user(session)

    user: User | None = None
    cookie = request.cookies.get(settings.session_cookie_name)
    if cookie:
        uid = read_session(cookie)
        if uid is not None:
            user = await session.get(User, uid)
    if user is None:
        header = request.headers.get("authorization", "")
        if header.lower().startswith("bearer "):
            token = header[7:].strip()
            if token:
                user = (
                    await session.execute(select(User).where(User.token_hash == hash_token(token)))
                ).scalar_one_or_none()
    if user is None or not user.is_active:
        raise _unauthorized()
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def require_admin(user: CurrentUser) -> User:
    if user.role != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail={"code": "forbidden", "message": "Admin role required."})
    return user


AdminUser = Annotated[User, Depends(require_admin)]
