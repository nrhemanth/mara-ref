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

import csv
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from mara.preflight import confirm_deck_state
from mara.runtime import CapyClient, TERMINAL_STATUSES

from hardware.hp_rct5 import IkaRct5

HERE = Path(__file__).resolve().parent

TIMER_START_RE = re.compile(r"TIMER_START sample=(\S+) anneal_min=([\d.]+)")


def read_sample_data(csv_path: Path) -> list[dict]:
    """Read sample_id/temperature/anneal_min rows from a CSV."""
    with csv_path.open(newline="") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise ValueError(f"{csv_path} has no data rows")
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


def start_heater(port: str, celsius: float) -> None:
    with IkaRct5(port) as heater:
        print(f"IKA heater on {port}: name={heater.get_name()!r}, setting {celsius:.1f} C and starting")
        heater.set_setpoint_temperature(celsius)
        heater.start_heating()


def _parse_timestamp(value: str) -> datetime:
    """Parse an ISO-8601 timestamp from the Opentrons HTTP API (or the mock)."""
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


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

    cursor = 0
    while True:
        page = capy.list_commands(run_id, cursor=cursor)
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
            fired_at = _parse_timestamp(completed_at) if completed_at else datetime.now(timezone.utc)
            fire_time = fired_at + timedelta(minutes=anneal_min)
            ready_at[sample_id] = fire_time
            print(
                f"[{datetime.now():%H:%M:%S}] timer started for sample {sample_id} "
                f"({anneal_min:g} min) -- ready at {fire_time.astimezone():%H:%M:%S}",
                file=out,
            )
        cursor += len(page.data)

        # Report any samples whose pickup time has come.
        now = datetime.now(timezone.utc)
        due = [sid for sid, t in ready_at.items() if t <= now]
        for sid in due:
            print(f"[{datetime.now():%H:%M:%S}] sample {sid} is ready for pickup!", file=out)
            del ready_at[sid]

        run_finished = capy.get_run(run_id).status in TERMINAL_STATUSES
        if run_finished and len(seen) >= len(anneal_by_id) and not ready_at:
            return
        time.sleep(poll_interval)


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

        for snap in capy.stream_status(run.id, poll_interval=0.5):
            print(f"  status: {snap.status}")
            if snap.status in TERMINAL_STATUSES:
                break
        print(f"final: {snap.status}")
        if snap.status != "succeeded":
            return 2

        # Step 4: watch for TIMER_START markers and report pickup times as they come due.
        track_pickup_timers(capy, run.id, rows)
        return 0


if __name__ == "__main__":
    protocol_file = Path(sys.argv[1])
    csv_file = Path(sys.argv[2])

    if not protocol_file.is_file():
        raise SystemExit(f"File {protocol_file} not found")
    if not csv_file.is_file():
        raise SystemExit(f"File {csv_file} not found")

    sys.exit(main(protocol_file, csv_file))
