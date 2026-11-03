"""Operational commands.

python -m app.cli create-user --email me@example.com --name "Me" [--admin]
python -m app.cli rotate-token --email me@example.com
python -m app.cli seed-demo [--count 60]      # requires DEMO_MODE=true
python -m app.cli purge-demo
python -m app.cli rescore
python -m app.cli reset-leads --yes            # delete ALL leads/calls/jobs (keeps users, settings, DNC list)
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
    cities = ["Sofia", "Plovdiv", "Varna"]
    per_city = max(5, count // len(cities))
    async with session_scope() as session:
        for city in cities:
            await enqueue(
                session,
                JobKind.SEARCH,
                {"location": city, "target_leads": per_city, "max_queries": 10, "use_neighborhoods": False},
            )
    await run_jobs_until_idle()
    async with get_sessionmaker()() as session:
        total = len((await session.execute(select(Business.id).where(Business.is_demo.is_(True)))).all())
    print(f"Demo data ready: {total} synthetic businesses")


async def purge_demo() -> None:
    async with session_scope() as session:
        result = await session.execute(delete(Business).where(Business.is_demo.is_(True)))
    print(f"Deleted {result.rowcount} demo businesses")  # type: ignore[attr-defined]


async def reset_leads() -> None:
    from app.services.reset import reset_lead_data

    async with get_sessionmaker()() as session:
        counts = await reset_lead_data(session)
    print("Deleted " + ", ".join(f"{n} {label}" for label, n in counts.items()))


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
    p = sub.add_parser("reset-leads")
    p.add_argument("--yes", action="store_true", help="confirm deleting every lead")
    p = sub.add_parser("dump-openapi")
    p.add_argument("path")
    args = parser.parse_args()

    if args.command == "dump-openapi":
        dump_openapi(args.path)
        return
    if args.command == "reset-leads" and not args.yes:
        print(
            "reset-leads deletes every lead, call, note and search job. Re-run with --yes.", file=sys.stderr
        )
        sys.exit(2)
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
            elif args.command == "reset-leads":
                await reset_leads()
        finally:
            await dispose_engine()

    asyncio.run(run())


if __name__ == "__main__":
    main()
