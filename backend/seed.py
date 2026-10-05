"""Seed script: creates the initial owner, default groups, sample contacts,
sample Q&A entries, and a default AppSettings row.

Run locally with:
    python seed.py

Env vars from .env are picked up automatically (pydantic-settings).

Override the owner email via OWNER_EMAIL env var (defaults to chetan@example.com).
"""
from __future__ import annotations

import os
from getpass import getpass

from app.config import get_settings
from app.db import SessionLocal, init_db
from app.models import (
    AppSettings,
    Contact,
    Group,
    Owner,
    QAEntry,
    ScopeType,
)
from app.routers.auth import _hash_password


OWNER_EMAIL = os.environ.get("OWNER_EMAIL", "chetan@example.com")


def _ensure_group(db, name, greeting, fallback, language="en-US"):
    grp = db.query(Group).filter(Group.name == name).one_or_none()
    if grp is None:
        grp = Group(
            name=name,
            greeting=greeting,
            fallback_message=fallback,
            language=language,
        )
        db.add(grp)
        db.flush()
    return grp


def _ensure_contact(db, *, name, phone, group, **fields):
    contact = (
        db.query(Contact).filter(Contact.phone_e164 == phone).one_or_none()
    )
    if contact is not None:
        return contact
    contact = Contact(name=name, phone_e164=phone, group_id=group.id, **fields)
    db.add(contact)
    db.flush()
    return contact


def _ensure_qa(db, *, title, examples, answer, scope_type, scope_id=None, language="en-US"):
    existing = (
        db.query(QAEntry).filter(QAEntry.title == title).one_or_none()
    )
    if existing is not None:
        return existing
    qa = QAEntry(
        title=title,
        example_questions="\n".join(examples),
        answer_text=answer,
        language=language,
        scope_type=scope_type,
        scope_id=scope_id,
        is_active=True,
    )
    db.add(qa)
    db.flush()
    return qa


def seed():
    s = get_settings()
    init_db()

    with SessionLocal() as db:
        # 1) Owner — create only if not present. Configurable via OWNER_EMAIL.
        owner = db.query(Owner).filter(Owner.email == OWNER_EMAIL).one_or_none()
        if owner is None:
            print(f"Creating owner account for {OWNER_EMAIL}...")
            pw = getpass(f"Set a password for {OWNER_EMAIL}: ")
            pw2 = getpass("Confirm password: ")
            if pw != pw2:
                print("Passwords do not match. Aborting.")
                return
            if len(pw) < 8:
                print("Password must be at least 8 characters. Aborting.")
                return
            owner = Owner(
                name=s.default_owner_name,
                email=OWNER_EMAIL,
                password_hash=_hash_password(pw),
                assistant_name=s.default_assistant_name,
            )
            db.add(owner)
            db.commit()
            db.refresh(owner)
            print(f"  Owner created (id={owner.id}). Use these credentials to log in to the app.")
        else:
            print(f"  Owner already exists (id={owner.id}, email={owner.email}).")

        # 2) Default groups.
        family = _ensure_group(
            db, "Family",
            "Hi, this is Chetan's AI assistant. He's busy right now. What would you like to ask?",
            "Chetan will call you back.",
        )
        _ensure_group(
            db, "Friends",
            "Hi, this is Chetan's AI assistant. He's busy right now. What would you like to ask?",
            "Chetan will call you back.",
        )
        college = _ensure_group(
            db, "College",
            "Hi, this is Chetan's AI assistant. He's busy right now. What would you like to ask?",
            "Chetan will call you back.",
        )
        _ensure_group(
            db, "Unknown",
            "Hi, this is Chetan's AI assistant. He's busy right now. What would you like to ask?",
            "Chetan will call you back.",
        )

        # 3) Sample contacts — only add if missing (placeholder phones — replace).
        mom = _ensure_contact(
            db,
            name="Mom",
            phone="+919999900001",
            group=family,
            relationship_label="Mother",
            language="en-US",
            is_vip=True,
            custom_greeting="Hi, this is Chetan's AI assistant. He's busy right now and will call you back soon.",
            custom_fallback="Chetan will call you back.",
        )
        _ensure_contact(
            db,
            name="Father",
            phone="+919999900002",
            group=family,
            relationship_label="Father",
            language="en-US",
        )
        rahul = _ensure_contact(
            db,
            name="Rahul",
            phone="+919999900003",
            group=college,
            relationship_label="Classmate",
            language="en-US",
        )

        # 4) Sample Q&A entries.
        _ensure_qa(
            db,
            title="When will you be back?",
            examples=["When will you be back?", "When are you coming home?", "Kab aaoge?"],
            answer="I'll be back by 8 PM today.",
            scope_type=ScopeType.CONTACT,
            scope_id=mom.id,
        )
        _ensure_qa(
            db,
            title="Are you free this weekend?",
            examples=["Are you free this weekend?", "Weekend pe free ho?", "Saturday ko kuch hai?"],
            answer="I'm free on Sunday after 2 PM.",
            scope_type=ScopeType.ALL,
        )
        _ensure_qa(
            db,
            title="What time is the project meeting?",
            examples=["What time is the project meeting?", "Project meeting kab hai?"],
            answer="The project meeting is at 4 PM on Monday.",
            scope_type=ScopeType.GROUP,
            scope_id=college.id,
        )
        _ensure_qa(
            db,
            title="Is the college assignment submitted?",
            examples=["Is the college assignment submitted?", "Assignment submit hua?"],
            answer="Yes, I submitted it on the college portal.",
            scope_type=ScopeType.GROUP,
            scope_id=college.id,
        )

        db.commit()

        # 5) AppSettings singleton.
        if db.get(AppSettings, 1) is None:
            db.add(AppSettings(id=1, assistant_enabled=True))
            db.commit()
            print("  Seeded AppSettings row.")

    print("\nSeed complete. Start the backend with:\n  uvicorn app.main:app --reload")


if __name__ == "__main__":
    seed()