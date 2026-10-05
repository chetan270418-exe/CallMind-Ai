# CallMind AI — Product Spec

> Personal AI call receptionist. Answers missed calls using only the
> answers the owner has pre-written. Logs every call. Always discloses
> that it's an AI.

This document is the source of truth for product, data, and API shape.
The 52-page Figma export (`Untitled_compressed.pdf`) is the visual
spec; this doc is the behaviour spec.

---

## 1. What the app is

CallMind AI is a personal AI call receptionist. When the owner misses a
call, the call is forwarded to a cloud number (Twilio). A backend answers
it, listens to the caller's one question, finds the matching answer the
owner pre-wrote, speaks it, and ends the call. If there is no matching
answer, it says the owner will call back. Every call is logged so the
owner can review it in a mobile app.

It is **not** a free-form chatbot. It retrieves answers the owner wrote;
it does not invent them.

- **Owner:** one person (single-user app for now).
- **Callers:** family, friends, college contacts, unknown numbers.

### Call flow

1. A call comes in and the owner doesn't answer.
2. The carrier forwards it to the cloud number (Twilio).
3. Twilio sends a webhook to the FastAPI backend (`/voice/incoming`).
4. The backend identifies the caller from the number.
5. The backend plays a greeting that says it is an AI assistant,
   personalised by caller.
6. The backend listens to the caller's question (Twilio `<Gather input="speech">`).
7. The backend matches it against the Q&A library for that caller or group.
8. If there is a match, it speaks the answer. If not, it says
   "Chetan will call you back".
9. The call ends. The backend saves the call to the log and flags it
   "needs callback" if unmatched.
10. The owner sees it in the app.

---

## 2. Feature list

### MVP (build first)

- Master switch: assistant ON / OFF
- Caller identification from contacts (name, relationship, group)
- Groups: Family, Friends, College, Unknown (the owner can add more)
- Q&A library: each entry has example questions, an answer, language, and
  who it applies to (everyone / a group / one contact)
- Personalised greeting per group or contact
- Fallback message, also personalisable per group or contact
- Call log with transcript, matched answer, match confidence, outcome
  and time
- "Needs callback" flag on unanswered calls, with a mark-as-done action
- Test screen: type a question, pick a caller, see which answer would be
  chosen
- Forwarding setup guide (codes for unanswered, busy, unreachable)
- AI disclosure line in the greeting

### Version 2

- Push notification after each handled call with a one-line summary
- Availability modes (College, Sleep, Meeting, Driving) with schedules
  and a different greeting per mode
- Hindi, Marathi and Hinglish support (language per Q&A and per contact)
- Voice choice (TTS voices) and speech speed
- Suggest-a-Q&A: tap an unmatched question to turn it into a new entry
- Repeat-caller alert (same number called 3 times in 10 minutes)
- Search and filter in call log and Q&A library
- Data retention settings

### Later / stretch

- Embedding-based matching
- Voice message option
- Spam / unknown labelling
- Statistics
- Optional on-device call answering (experimental)

---

## 3. Data model

| Table | Fields |
|---|---|
| owner | id, name, email, password_hash, assistant_name |
| groups | id, name, greeting, fallback_message, language |
| contacts | id, name, phone_e164, group_id, relationship, language, custom_greeting, custom_fallback, is_vip |
| qa_entries | id, title, example_questions, answer_text, language, scope_type, scope_id, is_active, times_used |
| calls | id, call_sid, caller_number, contact_id, group_id, started_at, duration_sec, transcript, matched_qa_id, match_score, answer_spoken, outcome, needs_callback, callback_done |
| app_settings | id, assistant_enabled, default_greeting, default_fallback, voice, speech_language, ai_disclosure_text, retention_days, match_threshold |

`qa_entries.scope_type` is one of `all`, `group`, `contact`. `scope_id`
holds the relevant group.id or contact.id, or NULL for `all`.

---

## 4. Matching rules

1. Pick Q&A candidates by scope: contact-specific > contact's group >
   everyone.
2. Score the caller's transcript against each candidate's
   `example_questions` using `rapidfuzz.fuzz.token_set_ratio`.
3. If the best score is above the threshold (default `0.60`), speak that
   answer. Outcome `ANSWERED`.
4. If not, speak the fallback for the contact or group. Outcome
   `FALLBACK`. Set `needs_callback = true`.
5. If the caller said nothing, outcome `NO_SPEECH`. Set
   `needs_callback = true`.
6. Never generate new facts. The matcher picks from existing entries.

---

## 5. Twilio webhook flow

```
caller dials owner's SIM
   -> no answer
   -> carrier forwards to TWILIO_FROM_NUMBER
   -> POST /voice/incoming {CallSid, From, To}
        - look up contact + group
        - log Call row (outcome=NO_SPEECH)
        - return TwiML: <Gather input="speech" action="/voice/answer">
                        <Say greeting /></Gather>
   -> Twilio plays greeting, records speech
   -> POST /voice/answer {CallSid, SpeechResult, ...}
        - score transcript against Q&A library
        - log transcript, matched_qa_id, match_score, answer_spoken
        - return TwiML: <Say answer_or_fallback /><Hangup />
   -> call ends
   -> POST /voice/status {CallSid, CallDuration, CallStatus}
        - update Call.duration_sec
```

---

## 6. API endpoints

### Twilio webhooks (no JWT; Twilio signature validated in production)

- `POST /voice/incoming`
- `POST /voice/answer`
- `POST /voice/status`

### App REST (JWT bearer)

- `POST /auth/login`              -> `{access_token, ...}`
- `GET   /auth/me`
- `GET/POST       /contacts`
- `GET/PUT/DELETE /contacts/{id}`
- `GET/POST       /groups`
- `GET/PUT/DELETE /groups/{id}`
- `GET/POST       /qa`
- `PUT/DELETE /qa   /qa/{id}`
- `POST /qa/test`                -> simulate a question
- `GET   /calls`                 -> filters: outcome, needs_callback,
                                     contact_id, since
- `GET   /calls/stats/summary`
- `GET   /calls/{id}`
- `PATCH /calls/{id}`            -> mark callback done
- `GET/PUT /settings`

---

## 7. Safety & trust

- Greeting always leads with "This is an AI assistant for [Name]".
- The matcher never invents. It picks from what the owner saved.
- Twilio signature verification on every webhook (production).
- App API is JWT-protected and rate-limited.
- All secrets in env vars; `.env` is gitignored.
- "Delete all data" action in Settings.

---

## 8. Out of scope for MVP

- Real-time push notifications (V2)
- Multilingual TTS / STT for Indian languages (V2)
- Embedding-based fuzzy matching (V2)
- On-device call answering on Android
- Group chat / multi-owner support
- Calling out / dialler functionality in the app