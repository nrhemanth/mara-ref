"""End-to-end film-drop-cast orchestration: heater (serial) -> OT-2 (HTTP API) -> pickup timers (this computer).

Usage (against the mock):
    capybara-mock-robot &
    python -m preruns.preflight_films protocols/mara_perovskite_user_edit.py samples.csv

Against Capy:
    ROBOT_URL=http://capy.local:31950 IKA_PORT=COM4 python -m preruns.preflight_films protocols/mara_perovskite_user_edit.py samples.csv

samples.csv must have one row per sample with columns: sample_id, temperature, anneal_min
  - temperature (deg C): must be the same value on every row -- there's one physical
    hotplate for the whole batch, not one setpoint per sample.
  - anneal_min: minutes after that sample's drop-cast dispense until it's ready to
    pick up. Samples don't all have the same anneal_min -- that's the whole point.

Steps:
  1. Regular preflight: snap the deck camera image, prompt the human to confirm.
  2. Read samples.csv, set the IKA hotplate to the shared temperature, start heating.
  3. Upload + play the protocol on the OT-2 (via the same Opentrons HTTP API
     CapyClient already wraps).
  4. Watch the run's command list for `protocol.comment("TIMER_START sample=<id>
     anneal_min=<min>")` markers (emitted by mara_perovskite_user_edit.py's
     drop_cast_single right after each sample's drop is dispensed), and report
     each sample's pickup time as it comes due.

Why polling instead of a push notification: the protocol executes on the OT-2's
own onboard HTTP server, not in this process, so a background thread inside the
protocol has no way to call back into this computer on its own. The only channel
this script has is the same HTTP API used to upload/run the protocol -- so
readiness is computed here, client-side, from (marker observed) + anneal_min,
not reported by the robot.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from mara.preflight import confirm_deck_state
from mara.runtime import CapyClient, CapyError, TERMINAL_STATUSES
from mara.timers import TIMER_START_RE, heater_setpoint, parse_timestamp, read_sample_data

from hardware.hp_rct5 import IkaRct5

HERE = Path(__file__).resolve().parent


def start_heater(port: str, celsius: float) -> None:
    with IkaRct5(port) as heater:
        print(f"IKA heater on {port}: name={heater.get_name()!r}, setting {celsius:.1f} C and starting")
        heater.set_setpoint_temperature(celsius)
        heater.start_heating()


def track_pickup_timers(
    capy: CapyClient,
    run_id: str,
    rows: list[dict],
    *,
    poll_interval: float = 2.0,
    out=sys.stdout,
) -> None:
    """Poll the run's commands for TIMER_START markers, then wait out and report
    each sample's pickup time as it comes due. Blocks until the run has finished
    AND every sample's anneal time has elapsed."""
    anneal_by_id = {str(r["sample_id"]): float(r["anneal_min"]) for r in rows}
    seen: set[str] = set()
    ready_at: dict[str, datetime] = {}

    # Re-list the whole command set every poll instead of paging through it
    # with an advancing cursor: the full list (queued/running/succeeded) is
    # known up front from analysis and never grows, so a cursor that only
    # moves forward would permanently skip any command that hadn't reached
    # "succeeded" yet at the moment its page was fetched -- there's no later
    # chance to revisit it. `seen` below dedups across polls.
    while True:
        try:
            page = capy.list_commands(run_id, cursor=0, page_length=10_000)
            run_finished = capy.get_run(run_id).status in TERMINAL_STATUSES
        except (httpx.HTTPError, CapyError) as exc:
            # A transient network blip talking to the robot shouldn't kill
            # pickup tracking outright -- retry instead of letting the poll
            # loop (and the thread it runs in) die silently mid-run.
            print(f"warning: pickup-timer poll failed ({exc!r}), retrying in {poll_interval:g}s", file=sys.stderr)
            time.sleep(poll_interval)
            continue

        for cmd in page.data:
            if cmd.status != "succeeded":
                continue  # only count a marker once it has actually executed
            params = getattr(cmd, "params", {}) or {}
            text = params.get("message") or params.get("text") or ""
            match = TIMER_START_RE.search(text)
            if not match:
                continue

            sample_id = match.group(1)
            if sample_id in seen:
                continue
            seen.add(sample_id)

            anneal_min = anneal_by_id.get(sample_id)
            if anneal_min is None:
                print(f"warning: TIMER_START for sample {sample_id} not in samples.csv, skipping", file=sys.stderr)
                continue

            completed_at = getattr(cmd, "completedAt", None)
            fired_at = parse_timestamp(completed_at) if completed_at else datetime.now(timezone.utc)
            fire_time = fired_at + timedelta(minutes=anneal_min)
            ready_at[sample_id] = fire_time
            print(
                f"[{datetime.now():%H:%M:%S}] timer started for sample {sample_id} "
                f"({anneal_min:g} min) -- ready at {fire_time.astimezone():%H:%M:%S}",
                file=out,
            )

        # Report any samples whose pickup time has come.
        now = datetime.now(timezone.utc)
        due = [sid for sid, t in ready_at.items() if t <= now]
        for sid in due:
            print(f"[{datetime.now():%H:%M:%S}] sample {sid} is ready for pickup!", file=out)
            del ready_at[sid]

        if run_finished and len(seen) >= len(anneal_by_id) and not ready_at:
            return
        time.sleep(poll_interval)


def start_tracker_thread(
    capy: CapyClient, run_id: str, rows: list[dict]
) -> tuple[threading.Thread, list[BaseException]]:
    """Run track_pickup_timers in a background thread. Thread.join() alone
    swallows exceptions raised inside a thread, which would make a crashed
    tracker look identical to one that finished successfully -- errors
    captures anything raised so the caller can re-raise it after joining."""
    errors: list[BaseException] = []

    def _target() -> None:
        try:
            track_pickup_timers(capy, run_id, rows)
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=_target, daemon=True)
    thread.start()
    return thread, errors


def main(protocol_file: Path, csv_file: Path) -> int:
    url = os.environ.get("ROBOT_URL", "http://192.168.1.101:31950")
    ika_port = os.environ.get("IKA_PORT", "COM4")

    rows = read_sample_data(csv_file)

    with CapyClient(url) as capy:
        capy.health()

        # Step 1: regular preflight -- snap the deck, prompt for confirmation.
        if not confirm_deck_state(capy, image_path=HERE / "preflight.jpg"):
            print("preflight not confirmed; aborting", file=sys.stderr)
            return 1

        # Step 2: read sample data, set the heater temperature, start heating.
        celsius = heater_setpoint(rows)
        start_heater(ika_port, celsius)

        # Step 3: upload + play the protocol to start the synthesis.
        protocol = capy.upload_protocol_with_csv(protocol_file, csv_file)
        print(f"uploaded {protocol.id}")

        run = capy.create_run(protocol.id)
        capy.run_action(run.id, "play")

        # Step 4: watch for TIMER_START markers and report pickup times as they
        # come due -- started now, concurrently with the run, not after it
        # finishes. track_pickup_timers polls until the run is terminal AND every
        # sample's anneal time has elapsed, so running it sequentially after the
        # status loop below would delay reporting short anneal_min samples (e.g.
        # 5 min) that come due while the protocol is still busy with later steps.
        timer_thread, timer_errors = start_tracker_thread(capy, run.id, rows)

        for snap in capy.stream_status(run.id, poll_interval=0.5):
            print(f"  status: {snap.status}")
            if snap.status in TERMINAL_STATUSES:
                break
        print(f"final: {snap.status}")
        if snap.status != "succeeded":
            return 2

        timer_thread.join()
        if timer_errors:
            raise timer_errors[0]
        return 0


if __name__ == "__main__":
    protocol_file = Path(sys.argv[1])
    csv_file = Path(sys.argv[2])

    if not protocol_file.is_file():
        raise SystemExit(f"File {protocol_file} not found")
    if not csv_file.is_file():
        raise SystemExit(f"File {csv_file} not found")

    sys.exit(main(protocol_file, csv_file))
