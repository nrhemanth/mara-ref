"""Persistent Temporal worker process. Must be running (after the Temporal
dev server, before any entry-point script) for FilmAnnealWorkflow to execute.

Usage:
    python -m mara.temporal.worker
    # or, once installed: mara-temporal-worker
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor

from temporalio.client import Client
from temporalio.worker import Worker

from . import activities
from .shared import TASK_QUEUE
from .workflows import FilmAnnealWorkflow

TEMPORAL_ADDRESS = "localhost:7233"


async def _run() -> None:
    client = await Client.connect(TEMPORAL_ADDRESS)
    with ThreadPoolExecutor(max_workers=20) as pool:
        worker = Worker(
            client,
            task_queue=TASK_QUEUE,
            workflows=[FilmAnnealWorkflow],
            activities=[
                activities.start_heater_activity,
                activities.upload_and_create_run_activity,
                activities.get_run_status_activity,
                activities.list_new_markers_activity,
                activities.notify_pickup_activity,
            ],
            activity_executor=pool,
        )
        print(f"worker listening on task queue {TASK_QUEUE!r} @ {TEMPORAL_ADDRESS}")
        await worker.run()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
