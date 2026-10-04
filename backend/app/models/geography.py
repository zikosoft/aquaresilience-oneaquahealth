"""P1.1 hotfix — countries/cities reference tables.

Schema foundation (D016): a `City`
carries its own default map center/zoom and EN/FR/ES labels, and `Country`
carries ISO codes, in the same pattern used elsewhere in the app for label
localization (English/French/Spanish columns rather than a separate
translation table, consistent with how the rest of the platform is
organized around 3 locked locales, not an open-ended set).
"""
from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, UniqueConstraint
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

    has_live_data: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    planned_data_source: Mapped[str | None] = mapped_column(String(160), nullable=True)

    country: Mapped["Country"] = relationship(back_populates="cities")
