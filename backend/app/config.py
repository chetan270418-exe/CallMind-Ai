"""Application configuration loaded from environment variables."""
from __future__ import annotations

import os
import secrets
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigError(RuntimeError):
    """Raised when the configuration is invalid for the current environment."""


class Settings(BaseSettings):
    """All runtime configuration.

    Values come from environment variables (or a local .env file in development).
    Never commit a real .env — only the .env.example.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Core
    app_name: str = "CallMind AI"
    environment: str = "development"  # development | production
    log_level: str = "INFO"

    # Database (Render provides DATABASE_URL automatically for managed Postgres)
    database_url: str = "sqlite:///./callmind.db"

    # Twilio
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""  # the CallMind number that receives forwarded calls

    # Auth
    jwt_secret: str = ""   # REQUIRED; enforced by auth module at startup
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24  # 1 day

    # Matching
    match_threshold: float = 0.60  # fuzzy match score 0..1

    # Voice defaults
    default_voice: str = "alice"
    speech_language: str = "en-US"

    # Owner defaults (used by seed)
    default_owner_name: str = "Chetan"
    default_assistant_name: str = "CallMind"
    default_greeting: str = (
        "Hi, this is Chetan's AI assistant. He's busy right now. "
        "What would you like to ask?"
    )
    default_fallback: str = "Chetan will call you back."
    ai_disclosure_text: str = "This is an AI assistant for Chetan"

    # Seed-time owner email. The seed script uses this (or the OWNER_EMAIL env
    # var) so the first owner can be created from anywhere — including the
    # Render dashboard after first deploy.
    default_owner_email: str = "chetan@example.com"


@lru_cache
def get_settings() -> Settings:
    s = Settings()

    # Production-time safety net: refuse to boot with a missing/weak JWT secret,
    # AND refuse to boot with a missing Twilio token (otherwise the webhooks
    # would silently accept unsigned calls in production).
    if s.environment.lower() == "production":
        missing: list[str] = []
        if not s.jwt_secret or len(s.jwt_secret) < 32:
            missing.append(
                "JWT_SECRET (must be >= 32 chars; generate with "
                "`python -c 'import secrets; print(secrets.token_urlsafe(48))'`)"
            )
        if not s.twilio_account_sid:
            missing.append("TWILIO_ACCOUNT_SID")
        if not s.twilio_auth_token:
            missing.append("TWILIO_AUTH_TOKEN")
        if not s.twilio_from_number:
            missing.append("TWILIO_FROM_NUMBER (e.g. +15551234567)")
        if missing:
            raise ConfigError(
                "Refusing to start in production with missing/invalid config:\n  - "
                + "\n  - ".join(missing)
            )

    # Dev-time convenience: generate an ephemeral JWT secret if none was provided.
    if not s.jwt_secret:
        s.jwt_secret = secrets.token_urlsafe(48)
    return s


def is_production() -> bool:
    return get_settings().environment.lower() == "production"


def is_twilio_configured() -> bool:
    s = get_settings()
    return bool(s.twilio_account_sid and s.twilio_auth_token and s.twilio_from_number)


# Convenience: read raw env without pydantic for places that need it before
# the Settings instance is built (e.g. logging config).
def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)