"""Twilio voice webhooks.

Endpoints (all POST, all validated by Twilio signature in production):
  /voice/incoming   - caller just arrived; greet and listen
  /voice/answer     - caller said something; match and reply
  /voice/status     - call ended; finalise the call row

The public base URL is read from RENDER_EXTERNAL_URL in production, or the
Host header in development (works behind ngrok / localtunnel).
"""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, Form, Request, Response
from sqlalchemy.orm import Session

from .. import models
from ..config import get_settings
from ..db import get_db
from ..services import caller_id, call_logger, matcher
from ..services.twiml import (
    greeting_and_listen,
    reject_call,
    speak_and_hangup,
)

router = APIRouter(prefix="/voice", tags=["twilio"])


def _verify_twilio_signature(request: Request) -> bool:
    """Validate the X-Twilio-Signature header.

    Only enforced when TWILIO_AUTH_TOKEN is configured AND we're in production.
    """
    from twilio.request_validator import RequestValidator

    s = get_settings()
    if not s.twilio_auth_token or s.environment.lower() != "production":
        # In development we accept unsigned webhooks so ngrok / curl tests work.
        return True

    validator = RequestValidator(s.twilio_auth_token)
    signature = request.headers.get("X-Twilio-Signature", "")
    # Build the full URL Twilio used (scheme + host + path).
    url = str(request.url)
    # Twilio signs the form-encoded body, so we need to pass it.
    form = dict(getattr(request, "_form", {}) or {})
    return validator.validate(url, form, signature)


def _public_base_url(request: Request) -> str:
    """Resolve the public base URL for absolute TwiML action targets."""
    s = get_settings()
    if s.environment.lower() == "production":
        base = os.environ.get("RENDER_EXTERNAL_URL") or str(request.base_url).rstrip("/")
    else:
        base = str(request.base_url).rstrip("/")
    return base.rstrip("/")


def _app_settings(db: Session) -> models.AppSettings | None:
    """Singleton app settings row (id=1)."""
    return db.query(models.AppSettings).filter(models.AppSettings.id == 1).one_or_none()


def _match_hints_for(contact, group, db) -> str | None:
    """Build a 'hints' string for Twilio Gather from eligible Q&A examples."""
    scopes: list[tuple[models.ScopeType, int | None]] = []
    if contact is not None:
        scopes.append((models.ScopeType.CONTACT, contact.id))
    if group is not None:
        scopes.append((models.ScopeType.GROUP, group.id))
    scopes.append((models.ScopeType.ALL, None))

    words: set[str] = set()
    for scope_type, scope_id in scopes:
        q = db.query(models.QAEntry).filter(models.QAEntry.is_active.is_(True))
        if scope_type == models.ScopeType.ALL:
            q = q.filter(models.QAEntry.scope_type == models.ScopeType.ALL)
        else:
            q = q.filter(
                models.QAEntry.scope_type == scope_type,
                models.QAEntry.scope_id == scope_id,
            )
        for entry in q.all():
            for line in (entry.example_questions or "").splitlines():
                for w in line.split():
                    w = w.strip(".,?!:;'\"")
                    if len(w) >= 3:
                        words.add(w)
    return ",".join(sorted(words))[:500] if words else None


@router.post("/incoming")
async def voice_incoming(
    request: Request,
    CallSid: str = Form(...),
    From: str = Form(""),
    db: Session = Depends(get_db),
):
    """First webhook when a forwarded call arrives."""
    # Twilio signature validation in production.
    if not _verify_twilio_signature(request):
        return Response(
            content=reject_call("Request signature could not be verified."),
            media_type="application/xml",
            status_code=403,
        )

    s = get_settings()
    settings_obj = _app_settings(db)

    contact, group = caller_id.lookup(db, From)

    # Resolve the caller's identity group (Unknown if we have no contact).
    if contact is None and group is None:
        group = caller_id.find_or_create_unknown_group(db)

    # Honour the master kill-switch.
    if settings_obj is not None and not settings_obj.assistant_enabled:
        call_logger.start_call(
            db,
            call_sid=CallSid,
            caller_number=From,
            contact_id=contact.id if contact else None,
            group_id=group.id if group else None,
        )
        return Response(content=reject_call(), media_type="application/xml")

    # Pick greeting + language.
    default_greeting = (
        settings_obj.default_greeting if settings_obj and settings_obj.default_greeting
        else s.default_greeting
    )
    default_language = (
        settings_obj.speech_language if settings_obj and settings_obj.speech_language
        else s.speech_language
    )
    voice = (
        settings_obj.voice if settings_obj and settings_obj.voice else s.default_voice
    )

    greeting = matcher.pick_greeting(contact, group, default_greeting)
    language = matcher.pick_language(contact, group, default_language)

    # Log the start (idempotent — if Twilio retries, we update the existing row).
    call_logger.start_call(
        db,
        call_sid=CallSid,
        caller_number=From,
        contact_id=contact.id if contact else None,
        group_id=group.id if group else None,
    )

    base = _public_base_url(request)
    twiml = greeting_and_listen(
        greeting,
        action_url=f"{base}/voice/answer",
        voice=voice,
        language=language,
        hints=_match_hints_for(contact, group, db),
    )
    return Response(content=twiml, media_type="application/xml")


@router.post("/answer")
async def voice_answer(
    request: Request,
    CallSid: str = Form(...),
    SpeechResult: str = Form(""),
    db: Session = Depends(get_db),
):
    """Caller has spoken — match their question against the Q&A library."""
    if not _verify_twilio_signature(request):
        return Response(
            content=speak_and_hangup("Request signature could not be verified."),
            media_type="application/xml",
            status_code=403,
        )

    s = get_settings()
    settings_obj = _app_settings(db)

    call = (
        db.query(models.Call).filter(models.Call.call_sid == CallSid).one_or_none()
    )
    if call is None:
        return Response(
            content=speak_and_hangup("Goodbye."),
            media_type="application/xml",
        )

    contact = (
        db.query(models.Contact).filter(models.Contact.id == call.contact_id).one_or_none()
        if call.contact_id else None
    )
    group = (
        db.query(models.Group).filter(models.Group.id == call.group_id).one_or_none()
        if call.group_id else None
    )

    transcript = (SpeechResult or "").strip()
    voice = (settings_obj.voice if settings_obj and settings_obj.voice else s.default_voice)
    language = (
        settings_obj.speech_language if settings_obj and settings_obj.speech_language
        else s.speech_language
    )
    default_fallback = (
        settings_obj.default_fallback if settings_obj and settings_obj.default_fallback
        else s.default_fallback
    )

    if not transcript:
        fallback = matcher.pick_fallback(contact, group, default_fallback)
        call_logger.record_answer(
            db,
            call_sid=CallSid,
            transcript="",
            matched_qa_id=None,
            match_score=0.0,
            answer_spoken=fallback,
            outcome=models.CallOutcome.NO_SPEECH,
            needs_callback=True,
        )
        return Response(
            content=speak_and_hangup(fallback, voice=voice, language=language),
            media_type="application/xml",
        )

    # Use the stored threshold even if it is 0 — only fall back to the env
    # default when there is no settings row at all yet.
    if settings_obj and settings_obj.match_threshold is not None:
        threshold = settings_obj.match_threshold
    else:
        threshold = s.match_threshold
    result = matcher.find_best(db, transcript, contact, group, threshold)

    if result.matched and result.qa is not None:
        call_logger.record_answer(
            db,
            call_sid=CallSid,
            transcript=transcript,
            matched_qa_id=result.qa.id,
            match_score=result.score,
            answer_spoken=result.answer_text,
            outcome=models.CallOutcome.ANSWERED,
            needs_callback=False,
        )
        return Response(
            content=speak_and_hangup(result.answer_text, voice=voice, language=language),
            media_type="application/xml",
        )

    fallback = matcher.pick_fallback(contact, group, default_fallback)
    call_logger.record_answer(
        db,
        call_sid=CallSid,
        transcript=transcript,
        matched_qa_id=None,
        match_score=result.score,
        answer_spoken=fallback,
        outcome=models.CallOutcome.FALLBACK,
        needs_callback=True,
    )
    return Response(
        content=speak_and_hangup(fallback, voice=voice, language=language),
        media_type="application/xml",
    )


@router.post("/status")
async def voice_status(
    request: Request,
    CallSid: str = Form(...),
    CallDuration: str = Form("0"),
    CallStatus: str = Form(""),
    db: Session = Depends(get_db),
):
    """Twilio tells us the call is over — finalise the row."""
    if not _verify_twilio_signature(request):
        return {"ok": False, "error": "invalid signature"}, 403

    try:
        duration = int(CallDuration or "0")
    except ValueError:
        duration = 0

    call_logger.finish_call(db, call_sid=CallSid, duration_sec=duration)
    return {
        "ok": True,
        "call_sid": CallSid,
        "duration_sec": duration,
        "status": CallStatus,
    }