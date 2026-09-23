"""P1.1 hotfix — countries/cities reference tables.

Schema foundation only (D016, decided with the user in Session 004): this
deployment remains single-city (Toulouse) for the hackathon — no city
switching UI/logic is built on top of these tables yet. They exist now so a
future multi-city iteration doesn't need a breaking schema change: a
`City` already carries its own default map center/zoom and EN/FR/ES labels,
and `Country` already carries ISO codes, in the same pattern used
elsewhere in the app for label localization (English/French/Spanish
columns rather than a separate translation table, consistent with how the
rest of the platform is organized around 3 locked locales, not an
open-ended set).

Nothing in the running app reads these tables yet (Settings > General's
`city` field stays the free-text string it always was); they are seeded
with exactly one row each (France / Toulouse) alongside the existing demo
seed data.
"""
from __future__ import annotations

import uuid

from sqlalchemy import Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class Country(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "countries"

    iso2: Mapped[str] = mapped_column(String(2), unique=True, nullable=False)
    iso3: Mapped[str] = mapped_column(String(3), unique=True, nullable=False)
    label_en: Mapped[str] = mapped_column(String(128), nullable=False)
    label_fr: Mapped[str] = mapped_column(String(128), nullable=False)
    label_es: Mapped[str] = mapped_column(String(128), nullable=False)

    cities: Mapped[list["City"]] = relationship(back_populates="country", cascade="all, delete-orphan")


class City(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "cities"
    __table_args__ = (UniqueConstraint("country_id", "label_en", name="uq_city_country_label_en"),)

    country_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("countries.id", ondelete="CASCADE"), nullable=False
    )
    label_en: Mapped[str] = mapped_column(String(128), nullable=False)
    label_fr: Mapped[str] = mapped_column(String(128), nullable=False)
    label_es: Mapped[str] = mapped_column(String(128), nullable=False)

    # Foundation for the future Settings > Map tab (P2): a city already
    # knows its own sensible map default, so wiring that tab up later is a
    # read, not a new schema change.
    default_lon: Mapped[float] = mapped_column(Float, nullable=False)
    default_lat: Mapped[float] = mapped_column(Float, nullable=False)
    default_zoom: Mapped[int] = mapped_column(Integer, nullable=False, default=11)

    country: Mapped["Country"] = relationship(back_populates="cities")
