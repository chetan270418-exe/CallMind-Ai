"""Q&A CRUD + test endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..config import get_settings
from ..db import get_db
from ..services import matcher
from .auth import current_owner

router = APIRouter(prefix="/qa", tags=["qa"])


def _qa_to_out(qa: models.QAEntry) -> schemas.QAOut:
    examples = [e.strip() for e in (qa.example_questions or "").splitlines() if e.strip()]
    return schemas.QAOut(
        id=qa.id,
        title=qa.title,
        example_questions=examples,
        answer_text=qa.answer_text,
        language=qa.language,
        scope_type=qa.scope_type,
        scope_id=qa.scope_id,
        is_active=qa.is_active,
        times_used=qa.times_used,
        created_at=qa.created_at,
    )


@router.get("", response_model=list[schemas.QAOut])
def list_qa(
    db: Session = Depends(get_db),
    _: models.Owner = Depends(current_owner),
):
    rows = db.query(models.QAEntry).order_by(models.QAEntry.id.desc()).all()
    return [_qa_to_out(r) for r in rows]


@router.post("", response_model=schemas.QAOut, status_code=201)
def create_qa(
    body: schemas.QABase,
    db: Session = Depends(get_db),
    _: models.Owner = Depends(current_owner),
):
    qa = models.QAEntry(
        title=body.title,
        example_questions="\n".join(body.example_questions),
        answer_text=body.answer_text,
        language=body.language,
        scope_type=body.scope_type,
        scope_id=body.scope_id,
        is_active=body.is_active,
    )
    db.add(qa)
    db.commit()
    db.refresh(qa)
    return _qa_to_out(qa)


@router.put("/{qa_id}", response_model=schemas.QAOut)
def update_qa(
    qa_id: int,
    body: schemas.QABase,
    db: Session = Depends(get_db),
    _: models.Owner = Depends(current_owner),
):
    qa = db.get(models.QAEntry, qa_id)
    if qa is None:
        raise HTTPException(404, "Q&A not found")
    qa.title = body.title
    qa.example_questions = "\n".join(body.example_questions)
    qa.answer_text = body.answer_text
    qa.language = body.language
    qa.scope_type = body.scope_type
    qa.scope_id = body.scope_id
    qa.is_active = body.is_active
    db.commit()
    db.refresh(qa)
    return _qa_to_out(qa)


@router.delete("/{qa_id}", status_code=204)
def delete_qa(
    qa_id: int,
    db: Session = Depends(get_db),
    _: models.Owner = Depends(current_owner),
):
    qa = db.get(models.QAEntry, qa_id)
    if qa is None:
        raise HTTPException(404, "Q&A not found")
    db.delete(qa)
    db.commit()


@router.post("/test", response_model=schemas.QATestResult)
def test_qa(
    body: schemas.QATestRequest,
    db: Session = Depends(get_db),
    _: models.Owner = Depends(current_owner),
):
    """Simulate a caller's question against the Q&A library, without making a call.

    The Test Assistant screen in the app uses this to preview the matched answer.
    """
    s = get_settings()
    settings_obj = db.query(models.AppSettings).filter(models.AppSettings.id == 1).one_or_none()
    # Use the stored threshold even if it is 0 — only fall back to the env
    # default when there is no settings row at all yet.
    if settings_obj and settings_obj.match_threshold is not None:
        threshold = settings_obj.match_threshold
    else:
        threshold = s.match_threshold

    contact = (
        db.query(models.Contact).filter(models.Contact.id == body.contact_id).one_or_none()
        if body.contact_id else None
    )
    group = contact.group if contact else None
    if group is None:
        from ..services import caller_id
        group = caller_id.find_or_create_unknown_group(db)

    fallback = matcher.pick_fallback(
        contact,
        group,
        (settings_obj.default_fallback if settings_obj and settings_obj.default_fallback
         else s.default_fallback),
    )

    result = matcher.find_best(db, body.question, contact, group, threshold)
    if result.matched and result.qa is not None:
        return schemas.QATestResult(
            matched=True,
            qa_id=result.qa.id,
            score=result.score,
            threshold=threshold,
            answer_text=result.answer_text,
            fallback_text=fallback,
            source=result.source,
        )
    return schemas.QATestResult(
        matched=False,
        qa_id=None,
        score=result.score,
        threshold=threshold,
        answer_text="",
        fallback_text=fallback,
        source="fallback",
    )