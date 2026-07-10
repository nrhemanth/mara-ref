"""Temporal activities: the only place in mara.temporal allowed to do real I/O
(HTTP to the OT-2, serial to the heater, stdout/beep). Kept short-lived —
each activity is a single request/action, not a loop — so the durable
waiting/looping can live in the deterministic workflow body instead.
"""

from __future__ import annotations

import sys
from pathlib import Path

from temporalio import activity

from hardware.hp_rct5 import IkaRct5
from mara.runtime import CapyClient
from mara.timers import TIMER_START_RE

from .shared import CommandMarker, FilmAnnealInput, ListMarkersInput, MarkerPage, PickupNotice, RunHandle, RunStatusInput


@activity.defn
def start_heater_activity(input: FilmAnnealInput) -> None:
    with IkaRct5(input.ika_port) as heater:
        activity.logger.info(f"IKA heater on {input.ika_port}: name={heater.get_name()!r}, setting {input.celsius:.1f} C")
        heater.set_setpoint_temperature(input.celsius)
        heater.start_heating()


@activity.defn
def upload_and_create_run_activity(input: FilmAnnealInput) -> RunHandle:
    with CapyClient(input.robot_url) as capy:
        protocol = capy.upload_protocol_with_csv(Path(input.protocol_path), Path(input.csv_path))
        run = capy.create_run(protocol.id)
        capy.run_action(run.id, "play")
        return RunHandle(protocol_id=protocol.id, run_id=run.id)


@activity.defn
def get_run_status_activity(input: RunStatusInput) -> str:
    with CapyClient(input.robot_url) as capy:
        return capy.get_run(input.run_id).status


@activity.defn
def list_new_markers_activity(input: ListMarkersInput) -> MarkerPage:
    """One page of TIMER_START markers starting at `cursor`. Checks both
    params.message (real Opentrons API) and params.text (mock), per the
    real-vs-mock command shape difference documented in CLAUDE.md."""
    with CapyClient(input.robot_url) as capy:
        page = capy.list_commands(input.run_id, cursor=input.cursor)

    markers: list[CommandMarker] = []
    for cmd in page.data:
        if cmd.status != "succeeded":
            continue  # only count a marker once it has actually executed
        params = getattr(cmd, "params", {}) or {}
        text = params.get("message") or params.get("text") or ""
        match = TIMER_START_RE.search(text)
        if not match:
            continue
        sample_id = match.group(1)
        completed_at = getattr(cmd, "completedAt", None)
        if completed_at is None:
            continue  # marker command hasn't recorded a completion timestamp yet
        markers.append(CommandMarker(sample_id=sample_id, fired_at=completed_at))

    return MarkerPage(markers=markers, next_cursor=input.cursor + len(page.data))


@activity.defn
def notify_pickup_activity(notice: PickupNotice) -> None:
    _announce_pickup(notice)


def _announce_pickup(notice: PickupNotice) -> None:
    """Desktop/terminal notification for now. To hand pickup off to the Dobot
    E6 once it's ready, replace this function's body with the robot call --
    the activity's name/signature (and the workflow) never need to change,
    since only the fact that notify_pickup_activity ran is part of workflow
    history, not this function's implementation."""
    banner = f"SAMPLE {notice.sample_id} READY FOR PICKUP (anneal done at {notice.ready_at})"
    border = "=" * len(banner)
    print(f"\n{border}\n{banner}\n{border}\n", flush=True)
    try:
        import winsound

        winsound.Beep(1000, 400)
    except Exception:
        sys.stdout.write("\a")
        sys.stdout.flush()
