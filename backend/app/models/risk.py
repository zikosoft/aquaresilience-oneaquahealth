"""P2 — deterministic risk scoring and early warnings.

Per D008 (locked decision) and Stop Rule #7, the risk score itself is a pure
function of ingested measurements + the Settings > Risk Engine configuration
(see `app.services.risk_engine`) — AI is never a dependency for this
computation, only an optional explainer layered on top in P3.

A `Warning` is one early-warning lifecycle instance. The risk engine creates
one deterministically whenever the combined score first reaches MODERATE or
above (no open warning exists yet), keeps updating it in place while the
condition persists (without disturbing an operator's ACKNOWLEDGED status),
and auto-resolves it once the score drops back to LOW. Operators can also
acknowledge/resolve manually at any time via the API. The lifecycle
vocabulary (ACTIVE/ACKNOWLEDGED/RESOLVED) matches the one already locked in
the seeded `alerts` Settings category since P0.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User


class WarningSeverity(StrEnum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class WarningStatus(StrEnum):
    ACTIVE = "ACTIVE"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"


class Warning(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One early-warning lifecycle instance."""

    __tablename__ = "warnings"

    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=WarningStatus.ACTIVE.value)
    risk_score: Mapped[float] = mapped_column(Float, nullable=False)
    # Per-factor breakdown snapshot at the moment this warning was last
    # updated by the risk engine — lets the UI/API explain *why* without a
    # second round-trip (P2 "explainable risk" requirement).
    factors: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    message: Mapped[str] = mapped_column(String(512), nullable=False)

    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    acknowledged_by: Mapped["User | None"] = relationship(foreign_keys=[acknowledged_by_id])
    resolved_by: Mapped["User | None"] = relationship(foreign_keys=[resolved_by_id])
