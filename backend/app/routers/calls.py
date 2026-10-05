"""Call log endpoints (read-only + the small patch for marking callback done)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import models, schemas
from ..db import get_db
from .auth import current_owner

router = APIRouter(prefix="/calls", tags=["calls"])


def _call_to_out(call: models.Call, db: Session) -> schemas.CallOut:
    contact = (
        db.query(models.Contact).filter(models.Contact.id == call.contact_id).one_or_none()
        if call.contact_id else None
    )
    group = (
        db.query(models.Group).filter(models.Group.id == call.group_id).one_or_none()
        if call.group_id else None
    )
    qa = (
        db.query(models.QAEntry).filter(models.QAEntry.id == call.matched_qa_id).one_or_none()
        if call.matched_qa_id else None
    )
    return schemas.CallOut(
        id=call.id,
        call_sid=call.call_sid,
        caller_number=call.caller_number,
        caller_name=contact.name if contact else None,
        group_name=group.name if group else None,
        started_at=call.started_at,
        duration_sec=call.duration_sec,
        transcript=call.transcript,
        answer_spoken=call.answer_spoken,
        outcome=call.outcome,
        needs_callback=call.needs_callback,
        callback_done=call.callback_done,
        match_score=call.match_score,
        matched_qa_title=qa.title if qa else None,
    )


@router.get("", response_model=list[schemas.CallOut])
def list_calls(
    db: Session = Depends(get_db),
    _: models.Owner = Depends(current_owner),
    outcome: Optional[models.CallOutcome] = Query(None),
    needs_callback: Optional[bool] = Query(None),
    contact_id: Optional[int] = Query(None),
    since: Optional[datetime] = Query(None),
    limit: int = Query(100, le=500),
):
    q = db.query(models.Call).order_by(models.Call.started_at.desc())
    if outcome is not None:
        q = q.filter(models.Call.outcome == outcome)
    if needs_callback is not None:
        q = q.filter(models.Call.needs_callback == needs_callback)
    if contact_id is not None:
        q = q.filter(models.Call.contact_id == contact_id)
    if since is not None:
        q = q.filter(models.Call.started_at >= since)
    return [_call_to_out(c, db) for c in q.limit(limit).all()]


@router.get("/stats/summary", response_model=schemas.StatsSummary)
def stats_summary(
    db: Session = Depends(get_db),
    _: models.Owner = Depends(current_owner),
):
    total = db.query(models.Call).count()
    answered = db.query(models.Call).filter(models.Call.outcome == models.CallOutcome.ANSWERED).count()
    fallback = db.query(models.Call).filter(models.Call.outcome == models.CallOutcome.FALLBACK).count()
    needs_cb = db.query(models.Call).filter(
        models.Call.needs_callback.is_(True),
        models.Call.callback_done.is_(False),
    ).count()
    return schemas.StatsSummary(
        total_calls=total,
        answered_calls=answered,
        fallback_calls=fallback,
        needs_callback=needs_cb,
    )


@router.get("/{call_id}", response_model=schemas.CallOut)
def get_call(
    call_id: int,
    db: Session = Depends(get_db),
    _: models.Owner = Depends(current_owner),
):
    call = db.get(models.Call, call_id)
    if call is None:
        raise HTTPException(404, "Call not found")
    return _call_to_out(call, db)


@router.patch("/{call_id}", response_model=schemas.CallOut)
def patch_call(
    call_id: int,
    body: schemas.CallPatch,
    db: Session = Depends(get_db),
    _: models.Owner = Depends(current_owner),
):
    call = db.get(models.Call, call_id)
    if call is None:
        raise HTTPException(404, "Call not found")
    if body.callback_done is not None:
        call.callback_done = body.callback_done
    db.commit()
    db.refresh(call)
    return _call_to_out(call, db)