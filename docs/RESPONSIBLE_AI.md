# AquaResilience — Responsible AI

This document explains what the AI layer is allowed to do, what it is
explicitly never allowed to do, and how the platform stays safe and
usable if it fails. It exists because Track 6 sits close to public safety
(early warning) and the One Health mission (community wellbeing), where an
overconfident or hallucinated AI output is not a cosmetic bug.

## 1. The AI never calculates risk

The single rule the rest of this document follows from: **environmental
risk is computed by a deterministic, auditable formula
(`backend/app/services/risk_engine.py`), never by a language model.** The
AI is only ever handed the *already-computed* risk score and its factor
breakdown, as a structured snapshot, and asked to interpret it in plain
language. It cannot move the risk score, cannot invent a severity, and
cannot open, acknowledge or resolve an Early Warning. See
`docs/ARCHITECTURE.md` §2 for the full reasoning.

## 2. Structured, validated output — not a chatbot

The AI is asked for a fixed JSON shape (`SituationBriefOut`):
`situation`, `summary`, `drivers[]`, `zones_to_watch[]`,
`recommendations[]`, `confidence`, `limitations[]` — plus which provider
and model produced it. This is validated with Pydantic before it is ever
stored or shown; a response that doesn't match the schema is rejected
rather than displayed. There is deliberately **no free-form chat
interface** anywhere in the product — every AI output the user sees is
this same structured, reviewed shape, generated on a schedule (default
every 4 hours, one shared brief for everyone — never on every dashboard
load) or on a genuine risk event, never as an open-ended conversation a
user could steer.

## 3. Confidence and limitations are shown, not hidden

Every AI output carries its own `confidence` score and an explicit
`limitations` list, both surfaced in the UI next to the explanation itself
— the platform never presents an AI interpretation as more certain than
the model itself reported. If the available evidence is thin (e.g. a data
source is degraded), the brief is expected to say so rather than fill the
gap with invented certainty.

## 4. No medical, diagnostic or official emergency claims

Per the project's locked scope, the platform explicitly does not make
medical, diagnostic, or official-emergency-authority claims. It frames
impact along the One Health chain — environmental conditions → freshwater
ecosystem health → community exposure/wellbeing context → early warning →
resilience planning — as context and decision support for operators and
communities, not as a substitute for an official flood-alert authority or
a health service. The `recommendations` an AI brief produces are
resilience actions (e.g. "monitor zone X", "review pumping station
readiness"), not medical or individual-safety directives.

## 5. Graceful degradation is a tested requirement, not a hope

If the configured AI provider is unreachable, slow, returns invalid JSON,
or the account runs out of quota: the dashboard, the map, the risk score,
Early Warnings and the Scenario Simulator all keep working exactly as
before. Only the AI panel shows a clear, honest degraded-state message
("AI Monitoring unavailable" with the real error, never a silent stale
brief pretending to be current). This is verified with an automated test
that simulates a provider failure, **and** live-verified against a real
outage in this project's own sandbox (whose network policy blocks both
OpenAI and Anthropic outright) — the platform's core monitoring was
confirmed to keep functioning in that exact condition, not just in a
mocked test.

## 6. Cost and rate controls are enforced server-side

Every AI Provider configuration carries a `daily_request_ceiling` and a
`cooldown_seconds`, enforced by the backend regardless of trigger source —
a scheduled tick, a human clicking "refresh now", or an automatic
event-triggered analysis (fires only on a HIGH/CRITICAL
warning, gated by the exact same budget a human manual refresh is held to,
so an automated event can never spend more than a person could). This
protects both API cost and against a runaway trigger loop.

## 7. Secrets and provider choice

The AI provider (OpenAI or Anthropic), model, and API key are configurable
in Settings, never hard-coded. Once a key is saved, the frontend never
receives it again — the API only ever reports a configured/not-configured
status; the key is encrypted at rest and is backend-only. Provider/model
can be changed without changing application code, so the platform is not
tied to one vendor's uptime or pricing.

## 8. What this does *not* claim

This is a hackathon prototype, not a certified early-warning authority. It
does not claim regulatory/official flood-stage accuracy (the hydrology
factor is normalized against each station's own trailing 90-day observed
range, a relative/statistical fallback — official Vigicrues threshold
data could not be obtained during development; see the project's decision
log). It does not claim the AI's recommendations have been reviewed by a
domain expert. These limitations are stated here, and by design, an AI
output itself is expected to disclose its own uncertainty via
`confidence`/`limitations` rather than the product overstating what it
knows.
