"""Toulouse, Garonne at Pont-Neuf (O200004001): instantaneous water height.

Source: data.gouv.fr "Données aux stations hydrométriques", archive
stations_O.tar (one directory per station, one gzip CSV per year).
Columns: cdentite;dtmesure;hauteur;qualh;methh;conth;statuth, height in mm.
Timestamps are read as UTC.

Output: data/clean/toulouse_pontneuf_H.parquet, hourly index (UTC), with
  h_mm_last  last reading within the hour (what a live system would see)
  h_mm_max   highest reading within the hour (used to detect threshold crossings)
  n_obs      readings in the hour
"""
from __future__ import annotations

import gzip
import io
import os
import tarfile

import pandas as pd

from loaders.common import RAW, get, log, write_clean

STATION = "O200004001"
FIRST_YEAR = 1983
ARCHIVE_URL = os.getenv(
    "TOULOUSE_ARCHIVE_URL", "https://bnum.din.gouv.fr/mdrive/index.php/s/SaT3wXMkMnCwwrd/download"
)
RAW_DIR = RAW / "toulouse"


def _download_station_files() -> list:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    existing = sorted(RAW_DIR.glob(f"{STATION}_*.csv.gz"))
    if existing:
        log(f"    {len(existing)} yearly files already present, skipping download")
        return existing
    log(f"    streaming {ARCHIVE_URL}")
    r = get(ARCHIVE_URL, stream=True, timeout=600)
    if "html" in r.headers.get("Content-Type", "").lower():
        raise RuntimeError("archive URL returned an HTML page; set TOULOUSE_ARCHIVE_URL")
    r.raw.decode_content = True
    with tarfile.open(fileobj=r.raw, mode="r|*") as tf:
        for m in tf:
            parts = m.name.split("/")
            if m.isfile() and STATION in parts and m.name.endswith(".csv.gz"):
                (RAW_DIR / f"{STATION}_{parts[-1]}").write_bytes(tf.extractfile(m).read())
    return sorted(RAW_DIR.glob(f"{STATION}_*.csv.gz"))


def run() -> None:
    log("Toulouse: Pont-Neuf water height")
    frames = []
    for path in _download_station_files():
        year = int(path.name.split("_")[1][:4])
        if year < FIRST_YEAR:
            continue
        text = gzip.decompress(path.read_bytes()).decode("utf-8", errors="replace")
        df = pd.read_csv(io.StringIO(text), sep=";", usecols=["dtmesure", "hauteur", "qualh"])
        frames.append(df)
    raw = pd.concat(frames, ignore_index=True)
    raw["t"] = pd.to_datetime(raw["dtmesure"], utc=True, errors="coerce")
    raw["hauteur"] = pd.to_numeric(raw["hauteur"], errors="coerce")
    raw = raw.dropna(subset=["t", "hauteur"]).drop_duplicates("t").sort_values("t").set_index("t")
    hourly = raw["hauteur"].resample("h").agg(["last", "max", "count"])
    hourly.columns = ["h_mm_last", "h_mm_max", "n_obs"]
    hourly = hourly[hourly["n_obs"] > 0]
    quality = {str(k): int(v) for k, v in raw["qualh"].value_counts().items()}
    write_clean(hourly, "toulouse_pontneuf_H", "h_mm_last",
                {"station": STATION, "unit": "mm", "quality_code_counts": quality,
                 "raw_readings": int(len(raw))})


if __name__ == "__main__":
    run()
