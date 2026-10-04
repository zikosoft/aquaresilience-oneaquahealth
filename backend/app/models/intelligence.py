"""P3 — AI Resilience Intelligence.

`SituationBrief` is an append-only history of AI-generated analyses. There is
always exactly one *current* brief per city — the most recent row by
`generated_at` for a given `city_id` — satisfying the Master Spec §19 intent
("one shared stored brief for all users", "do not call the LLM on every
dashboard load", 6 analyses/day) at the city level rather than a single
platform-wide row: every viewer looking at the same city sees the same
brief, still generated on a shared schedule/budget (see
`AIProviderConfig.daily_request_ceiling`, unchanged), never a per-user/
per-load LLM call. Keeping history (rather than a single mutable row) costs
nothing extra and gives "last analysis" a real audit trail for free,
matching the same append-only pattern already used for
`Measurement`/`Warning`.

Scheduling/usage-control state (last run, last error, today's request count)
lives on `AIProviderConfig` itself (see `app.models.settings`) rather than
here, since that state describes *the job*, not any one brief — the same
place `scheduled_analysis_interval_minutes`/`daily_request_ceiling`/
`cooldown_seconds` already live.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class SituationBrief(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One validated AI Situation Brief — the OBSERVE→CORRELATE→INTERPRET→
    EXPLAIN→RECOMMEND pipeline's stored, schema-validated output (Master
    Spec §18). AI is an interpretive layer only: `risk_score_snapshot`/
    `risk_severity_snapshot` are copied from the deterministic Risk Engine
    (P2, D008) at generation time for display, never recomputed by the AI."""

    __tablename__ = "situation_briefs"

    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    city_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cities.id", ondelete="SET NULL"), nullable=True, index=True
    )
    language: Mapped[str] = mapped_column(String(8), nullable=False)
    triggered_by: Mapped[str] = mapped_column(String(16), nullable=False)  # "scheduled" | "manual" | "event"

    # --- validated structured output (Master Spec §18 JSON shape) ---
    situation: Mapped[str] = mapped_column(String(16), nullable=False)  # low|moderate|high|critical
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    drivers: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    zones_to_watch: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    recommendations: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    limitations: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    # --- deterministic context this brief explains (never derived by the AI) ---
    risk_score_snapshot: Mapped[float] = mapped_column(Float, nullable=False)
    risk_severity_snapshot: Mapped[str] = mapped_column(String(16), nullable=False)

    # --- provenance ---
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
