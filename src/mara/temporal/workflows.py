"""FilmAnnealWorkflow: durable orchestration of heater -> OT-2 run -> 16
concurrent per-sample anneal timers -> pickup notification.

No CapyClient/pyserial/stdin/print/datetime.now() in this module -- workflow
code must stay deterministic and replayable. All real I/O lives in
mara.temporal.activities; activities are invoked by name string so this
module's imports stay limited to shared DTOs and the SDK itself.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

from mara.timers import parse_timestamp

from .shared import FilmAnnealInput, ListMarkersInput, MarkerPage, PickupNotice, RunHandle, RunStatusInput

TERMINAL_STATUSES = {"stopped", "failed", "succeeded"}


@workflow.defn
class FilmAnnealWorkflow:
    @workflow.run
    async def run(self, input: FilmAnnealInput) -> None:
        await workflow.execute_activity(
            "start_heater_activity",
            input,
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=5),
        )

        run_handle: RunHandle = await workflow.execute_activity(
            "upload_and_create_run_activity",
            input,
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=RetryPolicy(maximum_attempts=5),
        )

        anneal_by_id = {s.sample_id: s.anneal_min for s in input.samples}
        seen: set[str] = set()
        sample_tasks: list[asyncio.Task] = []
        cursor = 0
        run_terminal = False

        async def sample_timer(sample_id: str, fired_at: str, anneal_min: float) -> None:
            fire_at = parse_timestamp(fired_at) + timedelta(minutes=anneal_min)
            delay = (fire_at - workflow.now()).total_seconds()
            if delay > 0:
                await asyncio.sleep(delay)
            await workflow.execute_activity(
                "notify_pickup_activity",
                PickupNotice(sample_id=sample_id, ready_at=fire_at.isoformat(), run_id=run_handle.run_id),
                start_to_close_timeout=timedelta(seconds=10),
                retry_policy=RetryPolicy(maximum_attempts=1),  # best-effort notification
            )

        while not run_terminal or len(seen) < len(anneal_by_id):
            page: MarkerPage = await workflow.execute_activity(
                "list_new_markers_activity",
                ListMarkersInput(robot_url=input.robot_url, run_id=run_handle.run_id, cursor=cursor),
                start_to_close_timeout=timedelta(seconds=15),
                retry_policy=RetryPolicy(maximum_attempts=10),
            )
            cursor = page.next_cursor
            for marker in page.markers:
                if marker.sample_id in seen:
                    continue
                if marker.sample_id not in anneal_by_id:
                    workflow.logger.warning(f"TIMER_START for unknown sample {marker.sample_id!r}, skipping")
                    seen.add(marker.sample_id)
                    continue
                seen.add(marker.sample_id)
                sample_tasks.append(
                    asyncio.create_task(sample_timer(marker.sample_id, marker.fired_at, anneal_by_id[marker.sample_id]))
                )

            if not run_terminal:
                status = await workflow.execute_activity(
                    "get_run_status_activity",
                    RunStatusInput(robot_url=input.robot_url, run_id=run_handle.run_id),
                    start_to_close_timeout=timedelta(seconds=15),
                    retry_policy=RetryPolicy(maximum_attempts=10),
                )
                run_terminal = status in TERMINAL_STATUSES

            await asyncio.sleep(input.poll_interval_seconds)

        if sample_tasks:
            await asyncio.gather(*sample_tasks)
