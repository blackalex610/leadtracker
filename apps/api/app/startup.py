"""One-time process initialisation shared by the long-running server (lifespan) and
serverless functions (lazily, on the first request of an instance)."""

from __future__ import annotations

import asyncio
from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from alembic import command
from app.api.deps import ensure_default_user
from app.config import Settings, get_settings
from app.core.enums import UserRole
from app.core.security import hash_token
from app.db import get_engine, get_sessionmaker
from app.log import configure_logging, get_logger, register_secret
from app.models import User
from app.services.presets import seed_builtin_presets

log = get_logger(__name__)

_API_DIR = Path(__file__).resolve().parent.parent
_MIGRATION_LOCK_ID = 7_345_002

_ready = False
_setup_problems: list[str] = []


def configure_process(settings: Settings) -> None:
    configure_logging(settings.log_level, settings.use_json_logs)
    for secret in (settings.provider_api_key, settings.pagespeed_api_key, settings.admin_token):
        if secret is not None:
            register_secret(secret.get_secret_value())
    if settings.cron_secret is not None:
        register_secret(settings.cron_secret.get_secret_value())
    register_secret(settings.secret_key.get_secret_value())


def _alembic_config() -> Config:
    config = Config(str(_API_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(_API_DIR / "alembic"))
    return config


async def migrate_to_head(engine: AsyncEngine) -> bool:
    """Apply pending migrations; concurrent instances serialise on an advisory lock.
    Returns True when migrations ran."""
    config = _alembic_config()
    head = ScriptDirectory.from_config(config).get_current_head()

    async with engine.connect() as conn:
        current = await conn.run_sync(lambda c: MigrationContext.configure(c).get_current_revision())
    if current == head:
        return False

    async with engine.connect() as lock_conn:
        await lock_conn.execute(text("SELECT pg_advisory_lock(:id)"), {"id": _MIGRATION_LOCK_ID})
        try:
            # alembic's env.py runs its own event loop, so it gets a thread of its own.
            await asyncio.to_thread(command.upgrade, config, "head")
        finally:
            await lock_conn.execute(text("SELECT pg_advisory_unlock(:id)"), {"id": _MIGRATION_LOCK_ID})
            await lock_conn.commit()
    log.info("migrations_applied", previous=current, head=head)
    return True


async def ensure_admin(session: AsyncSession, settings: Settings) -> None:
    """ADMIN_TOKEN (if set) is the source of truth for the bootstrap admin's token."""
    if settings.admin_token is None:
        return
    email = settings.admin_email.strip().lower()
    token_hash = hash_token(settings.admin_token.get_secret_value())
    user = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if user is None:
        session.add(User(email=email, name="Admin", role=UserRole.ADMIN.value, token_hash=token_hash))
    elif user.token_hash != token_hash or user.role != UserRole.ADMIN.value or not user.is_active:
        user.token_hash = token_hash
        user.role = UserRole.ADMIN.value
        user.is_active = True
    else:
        return
    try:
        await session.commit()
        log.info("admin_user_ensured", email=email)
    except IntegrityError:  # another instance created it concurrently
        await session.rollback()


async def _auth_problems(session: AsyncSession, settings: Settings) -> list[str]:
    if settings.auth_mode != "token":
        return []
    has_login = (
        await session.execute(
            select(User.id).where(User.token_hash.is_not(None), User.is_active.is_(True)).limit(1)
        )
    ).scalar_one_or_none()
    if has_login is None:
        return ["No user can log in yet: set ADMIN_TOKEN (and optionally ADMIN_EMAIL) and redeploy."]
    return []


async def initialise(
    settings: Settings | None = None,
    sessionmaker: async_sessionmaker[AsyncSession] | None = None,
) -> list[str]:
    """Migrate (when enabled), seed built-in data and the bootstrap admin.
    Returns remaining setup problems (empty when the app is usable)."""
    settings = settings or get_settings()
    problems = settings.setup_problems()
    if any("DATABASE_URL" in p for p in problems):
        return problems
    if settings.migrate_on_startup:
        await migrate_to_head(get_engine())
    sessionmaker = sessionmaker or get_sessionmaker()
    async with sessionmaker() as session:
        await seed_builtin_presets(session)
        try:
            await ensure_default_user(session)
        except IntegrityError:
            await session.rollback()
        await ensure_admin(session, settings)
        problems += await _auth_problems(session, settings)
    for problem in problems:
        log.error("setup_problem", problem=problem)
    return problems


async def ensure_ready() -> list[str]:
    """Idempotent per process; retried on the next request if it fails."""
    global _ready, _setup_problems
    if not _ready:
        _setup_problems = await initialise()
        _ready = True
    return _setup_problems


def reset_ready_state() -> None:
    """For tests."""
    global _ready, _setup_problems
    _ready = False
    _setup_problems = []
