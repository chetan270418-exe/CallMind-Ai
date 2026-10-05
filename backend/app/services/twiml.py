"""TwiML generation helpers.

TwiML is Twilio's XML vocabulary that controls what happens on a call. We keep
all TwiML construction in one place so the rest of the code never has to think
about XML escaping.
"""
from __future__ import annotations

from html import escape
from typing import Optional


def _say(text: str, voice: str = "alice", language: str = "en-US") -> str:
    """Build a <Say> element."""
    return (
        f'<Say voice="{escape(voice)}" language="{escape(language)}">'
        f'{escape(text)}'
        f'</Say>'
    )


def greeting_and_listen(
    greeting: str,
    *,
    action_url: str,
    voice: str = "alice",
    language: str = "en-US",
    timeout: int = 5,
    hints: Optional[str] = None,
) -> str:
    """Play greeting, then listen for the caller's question via Gather.

    The action_url receives the SpeechResult as form field 'SpeechResult'.
    """
    hints_attr = f' hints="{escape(hints)}"' if hints else ""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Response>'
        f'<Gather input="speech" timeout="{timeout}" '
        f'action="{escape(action_url)}" method="POST" '
        f'language="{escape(language)}"{hints_attr}>'
        f'{_say(greeting, voice, language)}'
        '</Gather>'
        # If caller is silent, end gracefully with the fallback.
        f'{_say("We did not receive any input. Goodbye.", voice, language)}'
        '<Hangup/>'
        '</Response>'
    )


def speak_and_hangup(
    text: str,
    *,
    voice: str = "alice",
    language: str = "en-US",
) -> str:
    """Speak a single reply, then hang up."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Response>'
        f'{_say(text, voice, language)}'
        '<Hangup/>'
        '</Response>'
    )


def reject_call(reason: str = "") -> str:
    """Reject / hang up without speaking."""
    inner = _say(reason) if reason else ""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Response>'
        f'{inner}'
        '<Hangup/>'
        '</Response>'
    )