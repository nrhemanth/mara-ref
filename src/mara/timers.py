"""Pure, I/O-free helpers for reading sample data and interpreting TIMER_START
markers. Shared by preruns/preflight_films.py (the original single-process
script) and mara.temporal (the Temporal-orchestrated version) so the two code
paths can't drift apart.
"""

from __future__ import annotations

import csv
import re
from datetime import datetime
from pathlib import Path

TIMER_START_RE = re.compile(r"TIMER_START sample=(\S+) anneal_min=([\d.]+)")


_COLUMN_ALIASES = {"sample_id": "ID", "anneal_min": "anneal_time"}


def read_sample_data(csv_path: Path) -> list[dict]:
    """Read sample_id/temperature/anneal_min rows from a CSV.

    Also accepts the ID/anneal_time column names used by BATCH_CSV in
    protocols/*_perovskite_test.py (e.g. input/test_MAPBI3's plan CSVs) --
    normalized to sample_id/anneal_min either way, so downstream code
    (track_pickup_timers, heater_setpoint) only has to deal with one shape.
    """
    with csv_path.open(newline="") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise ValueError(f"{csv_path} has no data rows")

    header = rows[0].keys()
    for canonical, alias in _COLUMN_ALIASES.items():
        if canonical not in header and alias in header:
            for row in rows:
                row[canonical] = row[alias]

    for col in ("sample_id", "temperature", "anneal_min"):
        if col not in rows[0]:
            raise ValueError(f"{csv_path} is missing required column '{col}'")
    return rows


def heater_setpoint(rows: list[dict]) -> float:
    """All samples share one physical hotplate, so every row's temperature must agree."""
    temps = {float(r["temperature"]) for r in rows}
    if len(temps) > 1:
        raise ValueError(f"samples.csv has inconsistent temperatures for one hotplate: {sorted(temps)}")
    return temps.pop()


def parse_timestamp(value: str) -> datetime:
    """Parse an ISO-8601 timestamp from the Opentrons HTTP API (or the mock)."""
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
