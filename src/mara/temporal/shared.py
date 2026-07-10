"""Dataclasses passed between the workflow and its activities.

Kept plain-dataclass and JSON-serializable (no datetime/Path objects) since
Temporal serializes every activity/workflow argument and return value into
workflow history.
"""

from __future__ import annotations

from dataclasses import dataclass, field

TASK_QUEUE = "mara-films"


@dataclass
class SampleRow:
    sample_id: str
    anneal_min: float


@dataclass
class FilmAnnealInput:
    robot_url: str
    ika_port: str
    protocol_path: str
    csv_path: str
    celsius: float
    samples: list[SampleRow]
    poll_interval_seconds: float = 20.0


@dataclass
class RunHandle:
    protocol_id: str
    run_id: str


@dataclass
class CommandMarker:
    sample_id: str
    fired_at: str  # ISO-8601 string


@dataclass
class MarkerPage:
    markers: list[CommandMarker] = field(default_factory=list)
    next_cursor: int = 0


@dataclass
class ListMarkersInput:
    robot_url: str
    run_id: str
    cursor: int


@dataclass
class RunStatusInput:
    robot_url: str
    run_id: str


@dataclass
class PickupNotice:
    sample_id: str
    ready_at: str
    run_id: str
