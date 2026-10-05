"""SQLAlchemy ORM models for CallMind AI.

Schema (matches the product spec):
  owner          - single-owner account
  groups         - Family, Friends, College, Unknown, ...
  contacts       - people with phone + group + relationship + custom greetings
  qa_entries     - owner-written answers with example questions + language + scope
  calls          - one row per handled call
  settings       - singleton row with assistant on/off, default greeting, etc.

Scope precedence for matching: contact-specific > group > everyone (qa_entries.scope_type='all').
"""
from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    Boolean as SA_Boolean,
    DateTime,
    Enum as SA_Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class ScopeType(str, enum.Enum):
    ALL = "all"
    GROUP = "group"
    CONTACT = "contact"


class CallOutcome(str, enum.Enum):
    ANSWERED = "answered"     # a Q&A match above threshold
    FALLBACK = "fallback"     # no match, fallback spoken
    NO_SPEECH = "no_speech"   # caller said nothing / hung up
    ERROR = "error"           # call failed


class Owner(Base):
    __tablename__ = "owner"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    email: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    assistant_name: Mapped[str] = mapped_column(String(80), default="CallMind")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    greeting: Mapped[str] = mapped_column(Text, default="")
    fallback_message: Mapped[str] = mapped_column(Text, default="")
    language: Mapped[str] = mapped_column(String(10), default="en")


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    phone_e164: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    group_id: Mapped[int | None] = mapped_column(ForeignKey("groups.id", ondelete="SET NULL"))
    relationship_label: Mapped[str] = mapped_column(String(60), default="")
    language: Mapped[str] = mapped_column(String(10), default="en")
    custom_greeting: Mapped[str] = mapped_column(Text, default="")
    custom_fallback: Mapped[str] = mapped_column(Text, default="")
    is_vip: Mapped[bool] = mapped_column(SA_Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class QAEntry(Base):
    __tablename__ = "qa_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    example_questions: Mapped[str] = mapped_column(Text, default="")  # newline-separated
    answer_text: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(10), default="en")
    scope_type: Mapped[ScopeType] = mapped_column(SA_Enum(ScopeType), default=ScopeType.ALL)
    scope_id: Mapped[int | None] = mapped_column(Integer)  # group.id or contact.id
    is_active: Mapped[bool] = mapped_column(SA_Boolean, default=True)
    times_used: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Call(Base):
    __tablename__ = "calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    call_sid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    caller_number: Mapped[str] = mapped_column(String(32), index=True)
    contact_id: Mapped[int | None] = mapped_column(ForeignKey("contacts.id", ondelete="SET NULL"))
    group_id: Mapped[int | None] = mapped_column(ForeignKey("groups.id", ondelete="SET NULL"))
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    duration_sec: Mapped[int] = mapped_column(Integer, default=0)
    transcript: Mapped[str] = mapped_column(Text, default="")
    matched_qa_id: Mapped[int | None] = mapped_column(ForeignKey("qa_entries.id", ondelete="SET NULL"))
    match_score: Mapped[float] = mapped_column(Float, default=0.0)
    answer_spoken: Mapped[str] = mapped_column(Text, default="")
    outcome: Mapped[CallOutcome] = mapped_column(SA_Enum(CallOutcome), default=CallOutcome.NO_SPEECH)
    needs_callback: Mapped[bool] = mapped_column(SA_Boolean, default=False)
    callback_done: Mapped[bool] = mapped_column(SA_Boolean, default=False)


class AppSettings(Base):
    """Singleton row (id=1) — global app settings stored in the DB."""
    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assistant_enabled: Mapped[bool] = mapped_column(SA_Boolean, default=True)
    default_greeting: Mapped[str] = mapped_column(Text, default="")
    default_fallback: Mapped[str] = mapped_column(Text, default="")
    voice: Mapped[str] = mapped_column(String(40), default="alice")
    speech_language: Mapped[str] = mapped_column(String(10), default="en-US")
    ai_disclosure_text: Mapped[str] = mapped_column(Text, default="")
    retention_days: Mapped[int] = mapped_column(Integer, default=30)
    match_threshold: Mapped[float] = mapped_column(Float, default=0.60)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )