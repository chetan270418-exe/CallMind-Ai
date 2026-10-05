"""Singleton app settings endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models, schemas
from ..db import get_db
from .auth import current_owner

router = APIRouter(prefix="/settings", tags=["settings"])


def _ensure_row(db: Session) -> models.AppSettings:
    row = db.query(models.AppSettings).filter(models.AppSettings.id == 1).one_or_none()
    if row is None:
        row = models.AppSettings(id=1)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def _to_out(row: models.AppSettings) -> schemas.SettingsOut:
    return schemas.SettingsOut.model_validate(row)


@router.get("", response_model=schemas.SettingsOut)
def get_settings_route(
    db: Session = Depends(get_db),
    _: models.Owner = Depends(current_owner),
):
    return _to_out(_ensure_row(db))


@router.put("", response_model=schemas.SettingsOut)
def put_settings(
    body: schemas.SettingsUpdate,
    db: Session = Depends(get_db),
    _: models.Owner = Depends(current_owner),
):
    row = _ensure_row(db)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return _to_out(row)