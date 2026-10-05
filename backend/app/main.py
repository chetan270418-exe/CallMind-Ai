"""FastAPI entry point for CallMind AI."""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .config import get_settings
from .db import init_db
from .routers import auth, calls, contacts, groups, qa, voice
from .routers import settings as settings_router

log = logging.getLogger("callmind")
logging.basicConfig(
    level=get_settings().log_level,
    format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
)


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title=s.app_name,
        version=__version__,
        description=(
            "Backend for CallMind AI — a personal AI call receptionist that uses "
            "only owner-written answers. Twilio handles the call; this service "
            "matches the caller's question against the Q&A library and replies."
        ),
    )

    # CORS: open in development so ngrok / curl can hit the API.
    # Tighten in production — the Android app does not need CORS at all, but a
    # future web admin might. Restrict to specific hosts via the
    # ALLOWED_ORIGINS env var (comma-separated). Defaults to a single locked
    # origin if unset.
    import os as _os
    if s.environment.lower() == "production":
        origins_env = _os.environ.get("ALLOWED_ORIGINS", "")
        allowed_origins = [o.strip() for o in origins_env.split(",") if o.strip()] or [
            "https://callmind.onrender.com",
        ]
        app.add_middleware(
            CORSMiddleware,
            allow_origins=allowed_origins,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=["Authorization", "Content-Type"],
            allow_credentials=True,
        )
    else:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.on_event("startup")
    def _startup():
        init_db()
        log.info("CallMind backend ready :: version=%s env=%s", __version__, s.environment)

    @app.get("/")
    def root():
        return {
            "service": s.app_name,
            "version": __version__,
            "environment": s.environment,
            "twilio_configured": bool(s.twilio_account_sid and s.twilio_auth_token),
        }

    @app.get("/health")
    def health():
        return {"ok": True}

    # Core routers — these are required. An ImportError here would mean a
    # broken repo, not an environment issue, so we let it propagate.
    app.include_router(voice.router)
    app.include_router(auth.router)
    app.include_router(contacts.router)
    app.include_router(groups.router)
    app.include_router(qa.router)
    app.include_router(calls.router)
    app.include_router(settings_router.router)

    return app


app = create_app()