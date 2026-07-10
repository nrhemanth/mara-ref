"""End-to-end film-drop-cast orchestration, Temporal-backed version of
preflight_films.py: heater (serial) -> OT-2 (HTTP API) -> durable per-sample
pickup timers, run by a Temporal workflow instead of this process's memory.

Requires, already running, in this order:
    1. temporal server start-dev --db-filename .temporal/dev.db
    2. python -m mara.temporal.worker   (or: mara-temporal-worker)

Usage (against the mock):
    mara-mock-robot &
    python -m mara.temporal.worker &
    python -m preruns.preflight_films_temporal protocols/mara_perovskite_user_edit.py samples.csv

Against real hardware:
    ROBOT_URL=http://capy.local:31950 IKA_PORT=COM4 \
        python -m preruns.preflight_films_temporal protocols/mara_perovskite_user_edit.py samples.csv

samples.csv schema: same as preflight_films.py (sample_id, temperature, anneal_min).

This script itself only does the one-shot preflight (parse CSV, snap deck
camera, block on human confirmation) and then hands the run off to
FilmAnnealWorkflow -- once started, the workflow (not this process) owns
tracking each sample's anneal timer, so this script can be killed/re-run
without losing in-flight state. See mara.temporal.workflows for the durable
part of the flow.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

from temporalio.client import Client

from mara.preflight import confirm_deck_state
from mara.runtime import CapyClient
from mara.temporal.shared import TASK_QUEUE, FilmAnnealInput, SampleRow
from mara.temporal.workflows import FilmAnnealWorkflow
from mara.timers import heater_setpoint, read_sample_data

HERE = Path(__file__).resolve().parent
TEMPORAL_ADDRESS = "localhost:7233"


async def main(protocol_file: Path, csv_file: Path) -> int:
    url = os.environ.get("ROBOT_URL", "http://192.168.1.101:31950")
    ika_port = os.environ.get("IKA_PORT", "COM4")

    rows = read_sample_data(csv_file)
    celsius = heater_setpoint(rows)  # fail fast, before touching Temporal at all

    with CapyClient(url) as capy:
        capy.health()
        if not confirm_deck_state(capy, image_path=HERE / "preflight.jpg"):
            print("preflight not confirmed; aborting", file=sys.stderr)
            return 1

    client = await Client.connect(TEMPORAL_ADDRESS)
    wf_input = FilmAnnealInput(
        robot_url=url,
        ika_port=ika_port,
        protocol_path=str(protocol_file),
        csv_path=str(csv_file),
        celsius=celsius,
        samples=[SampleRow(sample_id=str(r["sample_id"]), anneal_min=float(r["anneal_min"])) for r in rows],
    )
    handle = await client.start_workflow(
        FilmAnnealWorkflow.run,
        wf_input,
        id=f"film-anneal-{csv_file.stem}-{int(time.time())}",
        task_queue=TASK_QUEUE,
    )
    print(f"workflow started: {handle.id}")
    print(f"watch it at http://localhost:8233/namespaces/default/workflows/{handle.id}")
    await handle.result()
    print("workflow finished: all samples annealed and pickup notifications sent")
    return 0


if __name__ == "__main__":
    protocol_file = Path(sys.argv[1])
    csv_file = Path(sys.argv[2])

    if not protocol_file.is_file():
        raise SystemExit(f"File {protocol_file} not found")
    if not csv_file.is_file():
        raise SystemExit(f"File {csv_file} not found")

    sys.exit(asyncio.run(main(protocol_file, csv_file)))
