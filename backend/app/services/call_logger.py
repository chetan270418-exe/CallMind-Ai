"""Call logging helpers.

The Twilio webhook gives us three signals:
  - /voice/incoming : call just arrived (we create the Call row with NO_SPEECH)
  - /voice/answer   : caller said something (we update transcript + outcome)
  - /voice/status   : call ended (we update duration and final outcome)
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from .. import models


def start_call(
    db: Session,
    *,
    call_sid: str,
    caller_number: str,
    contact_id: int | None,
    group_id: int | None,
) -> models.Call:
    """Create a Call row at the start of an incoming call.

    Idempotent: if a Call with the same call_sid is present (Twilio retries
    webhooks), we update the existing row instead of creating a duplicate.
    """
    existing = (
        db.query(models.Call).filter(models.Call.call_sid == call_sid).one_or_none()
    )
    if existing is not None:
        # Update identity in case the second webhook arrived with a different
        # 'From' (e.g. caller-id refix).
        existing.caller_number = caller_number
        existing.contact_id = contact_id
        existing.group_id = group_id
        db.commit()
        db.refresh(existing)
        return existing

    call = models.Call(
        call_sid=call_sid,
        caller_number=caller_number,
        contact_id=contact_id,
        group_id=group_id,
        started_at=datetime.utcnow(),
        duration_sec=0,
        outcome=models.CallOutcome.NO_SPEECH,
    )
    db.add(call)
    db.commit()
    db.refresh(call)
    return call


def record_answer(
    db: Session,
    *,
    call_sid: str,
    transcript: str,
    matched_qa_id: int | None,
    match_score: float,
    answer_spoken: str,
    outcome: models.CallOutcome,
    needs_callback: bool,
) -> models.Call | None:
    """Update the call row after /voice/answer."""
    call: models.Call | None = (
        db.query(models.Call).filter(models.Call.call_sid == call_sid).one_or_none()
    )
    if call is None:
        return None
    call.transcript = transcript
    call.matched_qa_id = matched_qa_id
    call.match_score = match_score
    call.answer_spoken = answer_spoken
    call.outcome = outcome
    call.needs_callback = needs_callback

    # Increment times_used on the matched Q&A.
    if matched_qa_id is not None:
        qa = db.query(models.QAEntry).filter(models.QAEntry.id == matched_qa_id).one_or_none()
        if qa is not None:
            qa.times_used = (qa.times_used or 0) + 1

    db.commit()
    db.refresh(call)
    return call


def finish_call(db: Session, *, call_sid: str, duration_sec: int) -> models.Call | None:
    """Update the call row after /voice/status (call ended)."""
    call: models.Call | None = (
        db.query(models.Call).filter(models.Call.call_sid == call_sid).one_or_none()
    )
    if call is None:
        return None
    call.duration_sec = duration_sec
    db.commit()
    db.refresh(call)
    return call