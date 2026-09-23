"""P1.1 hotfix — countries/cities reference tables (D016): schema foundation
only, seeded with France/Toulouse. Verifies the seed is correct and
idempotent (mirrors the pattern already used for the environmental seed)."""
from __future__ import annotations

from sqlalchemy import select

from app.models.geography import City, Country
from app.seed.seed_geography import run as seed_geography_run


def test_geography_seed_creates_france_and_toulouse(db_session):
    seed_geography_run()

    france = db_session.execute(select(Country).where(Country.iso2 == "FR")).scalar_one()
    assert france.iso3 == "FRA"
    assert france.label_en == "France"
    assert france.label_fr == "France"
    assert france.label_es == "Francia"

    toulouse = db_session.execute(select(City).where(City.country_id == france.id)).scalar_one()
    assert toulouse.label_en == "Toulouse"
    assert toulouse.default_lon == 1.4442
    assert toulouse.default_lat == 43.6047
    assert toulouse.default_zoom == 11


def test_geography_seed_is_idempotent(db_session):
    seed_geography_run()
    seed_geography_run()

    countries = db_session.execute(select(Country)).scalars().all()
    cities = db_session.execute(select(City)).scalars().all()
    assert len(countries) == 1
    assert len(cities) == 1
