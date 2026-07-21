"""End-to-end demo: upload examples/home.py, preflight, run, stream status.

Usage (against the mock):
    mara-mock-robot &
    python -m examples.preflight_home

Against mara:
    ROBOT_URL=http://capy.local:31950 python -m preruns.preflight_home
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from mara.preflight import confirm_deck_state
from mara.runtime import CapyClient, TERMINAL_STATUSES
from mara.timers import read_sample_data

from preruns.preflight_films import start_tracker_thread

HERE = Path(__file__).resolve().parent

def main(protocol_file: Path, csv_file: Path | None)->int:
# def main(protocol_file: Path) -> int:
    url = os.environ.get("ROBOT_URL", "http://192.168.1.101:31950")
    with CapyClient(url) as capy:
        capy.health()
        protocol = capy.upload_protocol(protocol_file)
        print(f"uploaded {protocol.id}")

        if not confirm_deck_state(capy, image_path=HERE / "preflight.jpg"):
            print("preflight not confirmed; aborting", file=sys.stderr)
            return 1

        # samples.csv (sample_id, temperature, anneal_min) tells us how long
        # after each sample's drop-cast dispense it's ready to pick up -- read
        # it up front so we can watch for TIMER_START markers below.
        rows = read_sample_data(csv_file) if csv_file else None

        run = capy.create_run(protocol.id)
        capy.run_action(run.id, "play")

        # Tell the human, via the terminal, when each sample is ready to pick
        # up -- started now, concurrently with the run, not after it finishes.
        # track_pickup_timers polls until the run is terminal AND every sample's
        # anneal time has elapsed, so calling it only after the status loop
        # below would delay reporting short anneal_min samples (e.g. 5 min)
        # that come due while the protocol is still busy with later steps.
        timer_thread = timer_errors = None
        if rows:
            timer_thread, timer_errors = start_tracker_thread(capy, run.id, rows)

        for snap in capy.stream_status(run.id, poll_interval=0.5):
            print(f"  status: {snap.status}")
            if snap.status in TERMINAL_STATUSES:
                break
        print(f"final: {snap.status}")
        if snap.status != "succeeded":
            return 2

        if timer_thread:
            timer_thread.join()
            if timer_errors:
                raise timer_errors[0]
        return 0


# if __name__ == "__main__":
#     protocol_file = sys.argv[1]
#     if not Path(protocol_file).is_file():
#         raise SystemExit(f"File {protocol_file} not found")
#     sys.exit(main(Path(protocol_file)))

if __name__ == "__main__":
    protocol_file = Path(sys.argv[1])

    csv_file = Path(sys.argv[2]) if len(sys.argv) > 2 else None

    if not Path(protocol_file).is_file():
        raise SystemExit(f"File {protocol_file} not found")

    sys.exit(main(protocol_file, csv_file))
