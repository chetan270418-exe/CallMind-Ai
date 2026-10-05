"""Matching engine — picks the best Q&A entry for a caller's question.

Scope precedence (highest wins):
  1. contact-specific Q&A  (qa_entries where scope_type=CONTACT and scope_id=contact.id)
  2. group Q&A              (qa_entries where scope_type=GROUP   and scope_id=group.id)
  3. everyone Q&A          (qa_entries where scope_type=ALL)

Scoring: rapidfuzz's token_set_ratio over each entry's example_questions.
The highest score above the configured threshold wins. Otherwise we return a
fallback and the call is flagged for callback.

This module is pure — it does not commit to the DB. The caller (router) is
responsible for incrementing times_used and saving the Call row.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from rapidfuzz import fuzz, process
from sqlalchemy.orm import Session

from .. import models


@dataclass
class MatchResult:
    matched: bool
    qa: Optional[models.QAEntry]
    score: float
    source: str        # contact | group | everyone | fallback
    answer_text: str   # the spoken text (either the Q&A answer or the fallback)


def _best_score_for_entry(question: str, entry: models.QAEntry) -> float:
    """Score a single Q&A entry against the caller's question.

    We split each example question, score with token_set_ratio, take the max.
    rapidfuzz returns (match_str, score, key) where score is 0..100.
    """
    examples: list[str] = [
        e.strip() for e in (entry.example_questions or "").splitlines() if e.strip()
    ]
    if not examples:
        return 0.0
    _match, score, _key = process.extractOne(
        question,
        examples,
        scorer=fuzz.token_set_ratio,
    )
    # Score is 0..100; normalise to 0..1.
    return max(0.0, min(1.0, float(score) / 100.0))


def find_best(
    db: Session,
    question: str,
    contact: Optional[models.Contact],
    group: Optional[models.Group],
    threshold: float,
) -> MatchResult:
    """Pick the best Q&A in scope order, respecting the threshold."""
    if not question or not question.strip():
        return MatchResult(False, None, 0.0, "fallback", "")

    # Build the scope list in priority order, skipping Nones.
    scopes: list[tuple[str, int | None]] = []
    if contact is not None:
        scopes.append(("contact", contact.id))
    if group is not None:
        scopes.append(("group", group.id))
    scopes.append(("everyone", None))

    for source, scope_id in scopes:
        q = db.query(models.QAEntry).filter(models.QAEntry.is_active.is_(True))
        if source == "everyone":
            q = q.filter(models.QAEntry.scope_type == models.ScopeType.ALL)
        elif source == "group":
            q = q.filter(
                models.QAEntry.scope_type == models.ScopeType.GROUP,
                models.QAEntry.scope_id == scope_id,
            )
        else:  # contact
            q = q.filter(
                models.QAEntry.scope_type == models.ScopeType.CONTACT,
                models.QAEntry.scope_id == scope_id,
            )
        candidates: list[models.QAEntry] = q.all()
        if not candidates:
            continue

        scored = [(entry, _best_score_for_entry(question, entry)) for entry in candidates]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        top_entry, top_score = scored[0]
        if top_score >= threshold:
            return MatchResult(
                matched=True,
                qa=top_entry,
                score=top_score,
                source=source,
                answer_text=top_entry.answer_text,
            )

    # No scope produced a match above threshold. Surface the best score we saw
    # across all scopes so the UI can show how close we came, rather than
    # always reporting 0.0.
    best_overall_score = 0.0
    for source, scope_id in scopes:
        q = db.query(models.QAEntry).filter(models.QAEntry.is_active.is_(True))
        if source == "everyone":
            q = q.filter(models.QAEntry.scope_type == models.ScopeType.ALL)
        elif source == "group":
            q = q.filter(
                models.QAEntry.scope_type == models.ScopeType.GROUP,
                models.QAEntry.scope_id == scope_id,
            )
        else:
            q = q.filter(
                models.QAEntry.scope_type == models.ScopeType.CONTACT,
                models.QAEntry.scope_id == scope_id,
            )
        for entry in q.all():
            s = _best_score_for_entry(question, entry)
            if s > best_overall_score:
                best_overall_score = s
    return MatchResult(False, None, best_overall_score, "fallback", "")


def pick_fallback(
    contact: Optional[models.Contact],
    group: Optional[models.Group],
    default_fallback: str,
) -> str:
    """Choose the right fallback message: contact → group → default."""
    if contact and contact.custom_fallback:
        return contact.custom_fallback
    if group and group.fallback_message:
        return group.fallback_message
    return default_fallback


def pick_greeting(
    contact: Optional[models.Contact],
    group: Optional[models.Group],
    default_greeting: str,
) -> str:
    """Choose the right greeting: contact → group → default."""
    if contact and contact.custom_greeting:
        return contact.custom_greeting
    if group and group.greeting:
        return group.greeting
    return default_greeting


def pick_language(
    contact: Optional[models.Contact],
    group: Optional[models.Group],
    default: str = "en-US",
) -> str:
    if contact and contact.language:
        return contact.language
    if group and group.language:
        return group.language
    return default