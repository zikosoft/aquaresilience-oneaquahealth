"""P2.1: read-only geography reference data — currently just the single
seeded city (D016, Toulouse-only for the hackathon). Gated on MAP:VIEW
rather than SETTINGS:VIEW: every role that can see the map (Viewer,
Operator, Administrator) needs this to center it, not just Settings
editors — see `ResilienceMap.vue` and the Settings > Map tab, both of
which read it.

`/map-config` additionally folds in the Settings > Map tab's tile-provider
choice for the same reason: that choice lives in the generic AppSettings
store (SETTINGS:VIEW-gated, admin-editor concern), but the map itself must
render it for every role that can view the map, not just Settings editors.
Rather than loosen SETTINGS:VIEW, the map reads the *effective* config from
here instead."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.deps import require_permission
from app.core.database import get_db
from app.models.geography import City, Country
from app.models.settings import AppSetting, SettingCategory
from app.models.user import User
from app.schemas.geography import CityOut, MapConfigOut

router = APIRouter()

DEFAULT_TILE_PROVIDER = "osm"
DEFAULT_RISK_LAYER_OPACITY = 35


def _list_cities(db: Session) -> list[CityOut]:
    rows = db.execute(
        select(City, Country).join(Country, Country.id == City.country_id).order_by(City.label_en)
    ).all()
    return [
        CityOut(
            id=city.id,
            label_en=city.label_en,
            label_fr=city.label_fr,
            label_es=city.label_es,
            country_iso2=country.iso2,
            default_lon=city.default_lon,
            default_lat=city.default_lat,
            default_zoom=city.default_zoom,
        )
        for city, country in rows
    ]


@router.get("/cities", response_model=list[CityOut])
def list_cities(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("MAP", "VIEW")),
) -> list[CityOut]:
    return _list_cities(db)


@router.get("/map-config", response_model=MapConfigOut)
def get_map_config(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("MAP", "VIEW")),
) -> MapConfigOut:
    setting = db.execute(
        select(AppSetting).where(AppSetting.category == SettingCategory.MAP.value, AppSetting.key == "map")
    ).scalar_one_or_none()
    value = setting.value or {} if setting else {}
    tile_provider = value.get("tile_provider", DEFAULT_TILE_PROVIDER)
    risk_layer_opacity = value.get("risk_layer_opacity", DEFAULT_RISK_LAYER_OPACITY)
    return MapConfigOut(tile_provider=tile_provider, risk_layer_opacity=risk_layer_opacity, cities=_list_cities(db))
