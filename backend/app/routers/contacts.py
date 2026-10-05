"""Contacts CRUD."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models, schemas
from ..db import get_db
from .auth import current_owner

router = APIRouter(prefix="/contacts", tags=["contacts"])


def _hydrate(db: Session, contact: models.Contact) -> schemas.ContactOut:
    """Build the API response, resolving the group via a fresh query.

    Doing a fresh query (rather than touching the detached `contact.group`
    attribute) avoids stale-data surprises if the session was already closed,
    and keeps the model free of an ORM `relationship` (which was the source
    of a name-shadowing bug earlier).
    """
    co = schemas.ContactOut.model_validate(contact)
    if contact.group_id is None:
        co.group_name = None
    else:
        group = db.get(models.Group, contact.group_id)
        co.group_name = group.name if group else None
    return co


def _validate_group_id(db: Session, group_id: int | None) -> None:
    """Raise 422 if group_id is set but the group doesn't exist."""
    if group_id is None:
        return
    if db.get(models.Group, group_id) is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"group_id={group_id} does not exist",
        )


@router.get("", response_model=list[schemas.ContactOut])
def list_contacts(
    db: Session = Depends(get_db),
    _: models.Owner = Depends(current_owner),
):
    rows = db.query(models.Contact).order_by(models.Contact.name).all()
    return [_hydrate(db, r) for r in rows]


@router.post("", response_model=schemas.ContactOut, status_code=201)
def create_contact(
    body: schemas.ContactBase,
    db: Session = Depends(get_db),
    _: models.Owner = Depends(current_owner),
):
    _validate_group_id(db, body.group_id)
    contact = models.Contact(**body.model_dump(by_alias=True))
    db.add(contact)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A contact with this phone number already exists.",
        ) from exc
    db.refresh(contact)
    return _hydrate(db, contact)


@router.get("/{contact_id}", response_model=schemas.ContactOut)
def get_contact(
    contact_id: int,
    db: Session = Depends(get_db),
    _: models.Owner = Depends(current_owner),
):
    contact = db.get(models.Contact, contact_id)
    if contact is None:
        raise HTTPException(404, "Contact not found")
    return _hydrate(db, contact)


@router.put("/{contact_id}", response_model=schemas.ContactOut)
def update_contact(
    contact_id: int,
    body: schemas.ContactBase,
    db: Session = Depends(get_db),
    _: models.Owner = Depends(current_owner),
):
    contact = db.get(models.Contact, contact_id)
    if contact is None:
        raise HTTPException(404, "Contact not found")
    _validate_group_id(db, body.group_id)
    for k, v in body.model_dump(by_alias=True).items():
        setattr(contact, k, v)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A contact with this phone number already exists.",
        ) from exc
    db.refresh(contact)
    return _hydrate(db, contact)


@router.delete("/{contact_id}", status_code=204)
def delete_contact(
    contact_id: int,
    db: Session = Depends(get_db),
    _: models.Owner = Depends(current_owner),
):
    contact = db.get(models.Contact, contact_id)
    if contact is None:
        raise HTTPException(404, "Contact not found")
    db.delete(contact)
    db.commit()