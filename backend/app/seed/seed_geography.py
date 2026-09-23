"""P1.1 hotfix — seed the countries/cities reference tables (D016).

Idempotent: seeds exactly one country (France) and one city (Toulouse) if
they don't already exist, matching the deployment's actual scope for the
hackathon. Toulouse's default lon/lat/zoom mirror the values already used
as fallbacks in the frontend map component and `.env.example`, so this is
purely additive — nothing reads from these tables yet.
"""
from __future__ import annotations

import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.geography import City, Country


def run() -> None:
    db: Session = SessionLocal()
    try:
        france = db.execute(select(Country).where(Country.iso2 == "FR")).scalar_one_or_none()
        if france is None:
            france = Country(
                iso2="FR",
                iso3="FRA",
                label_en="France",
                label_fr="France",
                label_es="Francia",
            )
            db.add(france)
            db.flush()

        toulouse = db.execute(
            select(City).where(City.country_id == france.id, City.label_en == "Toulouse")
        ).scalar_one_or_none()
        if toulouse is None:
            db.add(
                City(
                    country_id=france.id,
                    label_en="Toulouse",
                    label_fr="Toulouse",
                    label_es="Toulouse",
                    default_lon=1.4442,
                    default_lat=43.6047,
                    default_zoom=11,
                )
            )
        db.commit()
        print("Geography seed: OK (France / Toulouse).", file=sys.stderr)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run()
