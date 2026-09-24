"""P1.1 hotfix, extended Session 018 — seed the countries/cities reference
tables (D016).

Idempotent: each country/city is created only if it doesn't already exist
(matched on iso2 / (country, label_en)), so re-running this is always safe.

Session 018 (user request): now seeds all 9 OneAquaHealth consortium
countries (verified live against oneaquahealth.eu/consortium/ — 14
partners, 9 countries), each with one representative city, so the header's
city selector has real entries to switch between. Only Toulouse has an
actual ingested connector (Hub'Eau + Open-Meteo) — `has_live_data=True`.
The other 8 are real, selectable cities (the map recenters on them, their
labels are localized) but `has_live_data=False`, so the dashboard shows an
honest "no live connector yet" state for them rather than reusing
Toulouse's numbers under a different label. `planned_data_source` notes a
candidate open hydrology API already identified for that country during
this research pass, where one was found.

Athens is used as Greece's representative city: ENORA Innovation's exact
city could not be confirmed from public sources, so the capital is used as
an honest placeholder rather than an invented city.
"""
from __future__ import annotations

import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.geography import City, Country

# (iso2, iso3, label_en, label_fr, label_es)
COUNTRIES = [
    ("FR", "FRA", "France", "France", "Francia"),
    ("PT", "PRT", "Portugal", "Portugal", "Portugal"),
    ("NO", "NOR", "Norway", "Norvège", "Noruega"),
    ("GR", "GRC", "Greece", "Grèce", "Grecia"),
    ("AT", "AUT", "Austria", "Autriche", "Austria"),
    ("ES", "ESP", "Spain", "Espagne", "España"),
    ("IT", "ITA", "Italy", "Italie", "Italia"),
    ("IL", "ISR", "Israel", "Israël", "Israel"),
    ("BE", "BEL", "Belgium", "Belgique", "Bélgica"),
]

# (country_iso2, label_en, label_fr, label_es, lon, lat, zoom, has_live_data, planned_data_source)
CITIES = [
    ("FR", "Toulouse", "Toulouse", "Toulouse", 1.4442, 43.6047, 11, True, None),
    ("PT", "Coimbra", "Coimbra", "Coimbra", -8.4256, 40.2033, 12, False, "SNIRH (Portuguese hydrometric network)"),
    ("NO", "Oslo", "Oslo", "Oslo", 10.7522, 59.9139, 11, False, "NVE HydAPI"),
    ("GR", "Athens", "Athènes", "Atenas", 23.7275, 37.9838, 11, False, None),
    ("AT", "Vienna", "Vienne", "Viena", 16.3738, 48.2082, 11, False, "eHYD / data.gv.at (open data portal)"),
    ("ES", "Barcelona", "Barcelone", "Barcelona", 2.1734, 41.3851, 11, False, None),
    ("IT", "Naples", "Naples", "Nápoles", 14.2681, 40.8518, 11, False, "Centro Funzionale Regione Campania (unverified)"),
    ("IL", "Holon", "Holon", "Holon", 34.7792, 32.0158, 12, False, None),
    ("BE", "Ghent", "Gand", "Gante", 3.7174, 51.0543, 12, False, "Waterinfo.be (VMM / MOW-HIC)"),
]


def run() -> None:
    db: Session = SessionLocal()
    try:
        country_by_iso2: dict[str, Country] = {}
        for iso2, iso3, label_en, label_fr, label_es in COUNTRIES:
            country = db.execute(select(Country).where(Country.iso2 == iso2)).scalar_one_or_none()
            if country is None:
                country = Country(iso2=iso2, iso3=iso3, label_en=label_en, label_fr=label_fr, label_es=label_es)
                db.add(country)
                db.flush()
            country_by_iso2[iso2] = country

        for iso2, label_en, label_fr, label_es, lon, lat, zoom, has_live_data, planned_source in CITIES:
            country = country_by_iso2[iso2]
            city = db.execute(
                select(City).where(City.country_id == country.id, City.label_en == label_en)
            ).scalar_one_or_none()
            if city is None:
                db.add(
                    City(
                        country_id=country.id,
                        label_en=label_en,
                        label_fr=label_fr,
                        label_es=label_es,
                        default_lon=lon,
                        default_lat=lat,
                        default_zoom=zoom,
                        has_live_data=has_live_data,
                        planned_data_source=planned_source,
                    )
                )
            else:
                # Keep an existing row's has_live_data/planned_data_source in
                # sync with this table on every startup (idempotent update,
                # not just idempotent insert) — e.g. Toulouse's row created
                # before Session 018 defaulted to has_live_data=false.
                city.has_live_data = has_live_data
                city.planned_data_source = planned_source
        db.commit()
        print(f"Geography seed: OK ({len(CITIES)} cities across {len(COUNTRIES)} countries).", file=sys.stderr)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run()
