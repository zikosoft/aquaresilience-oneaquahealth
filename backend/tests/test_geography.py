"""P1.1 hotfix — countries/cities reference tables
(D016), now seeded with all 9 OneAquaHealth consortium countries. Verifies
the seed is correct and idempotent (mirrors the pattern already used for
the environmental seed), and that only Toulouse is flagged has_live_data."""
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
    assert toulouse.has_live_data is True


def test_geography_seed_is_idempotent(db_session):
    seed_geography_run()
    seed_geography_run()

    countries = db_session.execute(select(Country)).scalars().all()
    cities = db_session.execute(select(City)).scalars().all()
    assert len(countries) == 9
    assert len(cities) == 9


def test_geography_seed_only_toulouse_has_live_data(db_session):
    seed_geography_run()

    cities = db_session.execute(select(City)).scalars().all()
    live = [c for c in cities if c.has_live_data]
    assert [c.label_en for c in live] == ["Toulouse"]

    oslo = db_session.execute(select(City).where(City.label_en == "Oslo")).scalar_one()
    assert oslo.has_live_data is False
    assert oslo.planned_data_source == "NVE HydAPI"
