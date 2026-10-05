"""Pydantic schemas for API request/response shapes."""
from __future__ import annotations

import re
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

from .models import CallOutcome, ScopeType


E164_REGEX = re.compile(r"^\+[1-9][0-9]{6,14}$")  # + then 7..15 ASCII digits, no leading zero


def validate_e164(value: str) -> str:
    """Return the value if it matches ASCII-only E.164, else raise ValueError.

    Phone numbers must be plain ASCII digits so they can be safely stored and
    compared across SQLite / Postgres / CSV exports. Rejects Unicode digits,
    whitespace, dashes, parentheses — anything that isn't +0-9.
    """
    if not value or not value.isascii():
        raise ValueError(
            f"phone number must contain only ASCII characters; got {value!r}"
        )
    if not E164_REGEX.match(value):
        raise ValueError(
            f"phone number must be in E.164 format: '+' followed by 7-15 ASCII digits "
            f"(e.g. +919876543210); got {value!r}"
        )
    return value


# ---------- Auth ----------

class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    owner_name: str
    assistant_name: str


# ---------- Group ----------

class GroupBase(BaseModel):
    name: str
    greeting: str = ""
    fallback_message: str = ""
    language: str = "en"


class GroupOut(GroupBase):
    id: int
    member_count: int = 0

    class Config:
        from_attributes = True


# ---------- Contact ----------

class ContactBase(BaseModel):
    model_config = {"populate_by_name": True}

    name: str = Field(..., min_length=1, max_length=120)
    phone_e164: str = Field(..., description="E.164 format, e.g. +919876543210")
    group_id: Optional[int] = None
    # DB column is `relationship_label` (renamed to avoid shadowing SQLAlchemy's
    # `relationship` symbol). The public API field stays `relationship` via
    # validation_alias so the Android client sees a stable name.
    relationship: str = Field(
        default="",
        max_length=60,
        validation_alias="relationship_label",
        serialization_alias="relationship",
    )
    language: str = "en"
    custom_greeting: str = ""
    custom_fallback: str = ""
    is_vip: bool = False

    @field_validator("phone_e164")
    @classmethod
    def _check_phone(cls, v: str) -> str:
        return validate_e164(v)


class ContactOut(ContactBase):
    id: int
    group_name: Optional[str] = None

    class Config:
        from_attributes = True


# ---------- Q&A ----------

class QABase(BaseModel):
    title: str
    example_questions: List[str] = []
    answer_text: str
    language: str = "en"
    scope_type: ScopeType = ScopeType.ALL
    scope_id: Optional[int] = None
    is_active: bool = True


class QAOut(QABase):
    id: int
    times_used: int = 0
    created_at: datetime

    class Config:
        from_attributes = True


class QATestRequest(BaseModel):
    question: str
    contact_id: Optional[int] = None  # None = unknown caller


class QATestResult(BaseModel):
    matched: bool
    qa_id: Optional[int] = None
    score: float
    threshold: float
    answer_text: str = ""
    fallback_text: str = ""
    source: str = ""  # contact | group | everyone | fallback


# ---------- Call ----------

class CallOut(BaseModel):
    id: int
    call_sid: str
    caller_number: str
    caller_name: Optional[str] = None
    group_name: Optional[str] = None
    started_at: datetime
    duration_sec: int
    transcript: str
    answer_spoken: str
    outcome: CallOutcome
    needs_callback: bool
    callback_done: bool
    match_score: float
    matched_qa_title: Optional[str] = None

    class Config:
        from_attributes = True


class CallPatch(BaseModel):
    callback_done: Optional[bool] = None


# ---------- Settings ----------

class SettingsOut(BaseModel):
    assistant_enabled: bool
    default_greeting: str
    default_fallback: str
    voice: str
    speech_language: str
    ai_disclosure_text: str
    retention_days: int
    match_threshold: float

    class Config:
        from_attributes = True


class SettingsUpdate(BaseModel):
    assistant_enabled: Optional[bool] = None
    default_greeting: Optional[str] = None
    default_fallback: Optional[str] = None
    voice: Optional[str] = None
    speech_language: Optional[str] = None
    ai_disclosure_text: Optional[str] = None
    retention_days: Optional[int] = Field(default=None, ge=1, le=3650)
    match_threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0)


# ---------- Stats ----------

class StatsSummary(BaseModel):
    total_calls: int
    answered_calls: int
    fallback_calls: int
    needs_callback: int