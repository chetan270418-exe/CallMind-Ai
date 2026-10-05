"""Groups CRUD."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models, schemas
from ..db import get_db
from .auth import current_owner

router = APIRouter(prefix="/groups", tags=["groups"])


def _hydrate(db: Session, g: models.Group) -> schemas.GroupOut:
    go = schemas.GroupOut.model_validate(g)
    go.member_count = db.query(models.Contact).filter(models.Contact.group_id == g.id).count()
    return go


@router.get("", response_model=list[schemas.GroupOut])
def list_groups(
    db: Session = Depends(get_db),
    _: models.Owner = Depends(current_owner),
):
    rows = db.query(models.Group).order_by(models.Group.name).all()
    return [_hydrate(db, g) for g in rows]


@router.post("", response_model=schemas.GroupOut, status_code=201)
def create_group(
    body: schemas.GroupBase,
    db: Session = Depends(get_db),
    _: models.Owner = Depends(current_owner),
):
    g = models.Group(**body.model_dump())
    db.add(g)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A group named {body.name!r} already exists.",
        ) from exc
    db.refresh(g)
    return _hydrate(db, g)


@router.put("/{group_id}", response_model=schemas.GroupOut)
def update_group(
    group_id: int,
    body: schemas.GroupBase,
    db: Session = Depends(get_db),
    _: models.Owner = Depends(current_owner),
):
    g = db.get(models.Group, group_id)
    if g is None:
        raise HTTPException(404, "Group not found")
    for k, v in body.model_dump().items():
        setattr(g, k, v)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A group named {body.name!r} already exists.",
        ) from exc
    db.refresh(g)
    return _hydrate(db, g)


@router.delete("/{group_id}", status_code=204)
def delete_group(
    group_id: int,
    db: Session = Depends(get_db),
    _: models.Owner = Depends(current_owner),
):
    g = db.get(models.Group, group_id)
    if g is None:
        raise HTTPException(404, "Group not found")
    db.delete(g)
    db.commit()