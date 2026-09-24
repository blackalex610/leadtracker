"""Vercel serverless function: the whole FastAPI backend (apps/api) behind /api/*.
See vercel.json and docs/deployment.md."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api"))

from app.serverless import app  # noqa: E402

__all__ = ["app"]
