"""Caller identification service.

Maps an E.164 phone number to a Contact (and through it, a Group). Returns
None for unknown numbers.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from .. import models


def normalise(number: str) -> str:
    """Best-effort E.164 normalisation.

    Strips EVERY non-digit character so '+91 98765 43210', '9876543210',
    '(022) 1234-5678' all compare correctly. Prefixes with '+' if missing.
    """
    if not number:
        return ""
    digits = "".join(ch for ch in number if ch.isdigit())
    if not digits:
        return ""
    return "+" + digits


def lookup(db: Session, caller_number: str) -> tuple[models.Contact | None, models.Group | None]:
    """Find the contact for a caller number. Returns (contact, group)."""
    if not caller_number:
        return None, None
    n = normalise(caller_number)
    # Match by the digits-only form, since stored phone_e164 is always '+digits'.
    digits_only = n.lstrip("+")
    contact = (
        db.query(models.Contact)
        .filter(models.Contact.phone_e164 == n)
        .one_or_none()
    )
    if contact is None:
        contact = (
            db.query(models.Contact)
            .filter(models.Contact.phone_e164 == digits_only)
            .one_or_none()
        )
    if contact is None:
        return None, None
    group = (
        db.query(models.Group).filter(models.Group.id == contact.group_id).one_or_none()
        if contact.group_id else None
    )
    return contact, group


def find_or_create_unknown_group(db: Session) -> models.Group:
    """Return the 'Unknown' group, creating it if it doesn't exist."""
    grp = db.query(models.Group).filter(models.Group.name == "Unknown").one_or_none()
    if grp is None:
        grp = models.Group(
            name="Unknown",
            greeting="",
            fallback_message="",
            language="en",
        )
        db.add(grp)
        db.commit()
        db.refresh(grp)
    return grp