"""Operational commands.

python -m app.cli create-user --email me@example.com --name "Me" [--admin]
python -m app.cli rotate-token --email me@example.com
python -m app.cli seed-demo [--count 60]      # requires DEMO_MODE=true
python -m app.cli purge-demo
python -m app.cli rescore
python -m app.cli dump-openapi out.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from sqlalchemy import delete, select

from app.config import get_settings
from app.core.enums import JobKind, UserRole
from app.core.security import generate_token, hash_token
from app.db import dispose_engine, get_sessionmaker, session_scope
from app.log import configure_logging
from app.models import Business, User
from app.services.presets import seed_builtin_presets
from app.worker.queue import enqueue
from app.worker.runner import Worker


async def create_user(email: str, name: str, admin: bool) -> None:
    token = generate_token()
    async with session_scope() as session:
        existing = (
            await session.execute(select(User).where(User.email == email.lower()))
        ).scalar_one_or_none()
        if existing:
            print(f"User {email} already exists (use rotate-token)", file=sys.stderr)
            sys.exit(1)
        session.add(
            User(
                email=email.lower(),
                name=name,
                role=(UserRole.ADMIN if admin else UserRole.SALES).value,
                token_hash=hash_token(token),
            )
        )
    print(f"Created {email}. Access token (shown once, store it safely):\n{token}")


async def rotate_token(email: str) -> None:
    token = generate_token()
    async with session_scope() as session:
        user = (await session.execute(select(User).where(User.email == email.lower()))).scalar_one_or_none()
        if user is None:
            print(f"No user {email}", file=sys.stderr)
            sys.exit(1)
        user.token_hash = hash_token(token)
    print(f"New access token for {email} (shown once):\n{token}")


async def run_jobs_until_idle() -> None:
    worker = Worker(get_sessionmaker(), concurrency=1)
    while await worker.run_once():
        pass


async def seed_demo(count: int) -> None:
    if not get_settings().demo_mode:
        print(
            "seed-demo requires DEMO_MODE=true (synthetic data must never mix with production data)",
            file=sys.stderr,
        )
        sys.exit(1)
    async with get_sessionmaker()() as session:
        await seed_builtin_presets(session)
    searches = [
        {"category": "gyms", "preset_key": "gyms", "location": "Sofia"},
        {"category": "beauty salons", "preset_key": "beauty", "location": "Sofia"},
        {"category": "barber shops", "preset_key": "barbers", "location": "Sofia"},
        {"category": "restaurants", "preset_key": "restaurants", "location": "Plovdiv"},
        {"category": "dentists", "preset_key": "dentists", "location": "Varna"},
    ]
    per_search = max(5, count // len(searches))
    async with session_scope() as session:
        for params in searches:
            await enqueue(session, JobKind.SEARCH, {**params, "max_results": per_search, "min_rating": None})
    await run_jobs_until_idle()
    async with get_sessionmaker()() as session:
        total = len((await session.execute(select(Business.id).where(Business.is_demo.is_(True)))).all())
    print(f"Demo data ready: {total} synthetic businesses")


async def purge_demo() -> None:
    async with session_scope() as session:
        result = await session.execute(delete(Business).where(Business.is_demo.is_(True)))
    print(f"Deleted {result.rowcount} demo businesses")  # type: ignore[attr-defined]


async def rescore() -> None:
    async with session_scope() as session:
        await enqueue(session, JobKind.RESCORE, {})
    await run_jobs_until_idle()
    print("Rescored all leads")


def dump_openapi(path: str) -> None:
    from app.main import create_app

    spec = create_app(with_lifespan=False).openapi()
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(spec, fh, indent=2, ensure_ascii=False)
    print(f"Wrote {path}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("create-user")
    p.add_argument("--email", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--admin", action="store_true")
    p = sub.add_parser("rotate-token")
    p.add_argument("--email", required=True)
    p = sub.add_parser("seed-demo")
    p.add_argument("--count", type=int, default=100)
    sub.add_parser("purge-demo")
    sub.add_parser("rescore")
    p = sub.add_parser("dump-openapi")
    p.add_argument("path")
    args = parser.parse_args()

    if args.command == "dump-openapi":
        dump_openapi(args.path)
        return
    configure_logging("WARNING")

    async def run() -> None:
        try:
            if args.command == "create-user":
                await create_user(args.email, args.name, args.admin)
            elif args.command == "rotate-token":
                await rotate_token(args.email)
            elif args.command == "seed-demo":
                await seed_demo(args.count)
            elif args.command == "purge-demo":
                await purge_demo()
            elif args.command == "rescore":
                await rescore()
        finally:
            await dispose_engine()

    asyncio.run(run())


if __name__ == "__main__":
    main()
