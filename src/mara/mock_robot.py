"""Stateful in-memory mock of the Opentrons HTTP API.

Implements the subset of /protocols, /runs, /runs/{id}/actions, /runs/{id},
/runs/{id}/commands, and /health that capybara drives. Suitable for:

- protocol development against a fake robot (`capybara-mock-robot` CLI),
- in-process integration tests via `httpx.ASGITransport`,
- reference behaviour for the contract we expect from a real Capy.

Run-state transitions are scheduled with `asyncio.create_task` after the
`play` action; the delay is `create_app(run_duration=...)`-configurable.
Tests typically pass `run_duration=0.0` and poll until terminal.
"""

from __future__ import annotations

import asyncio
import io
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Form, HTTPException, Response, UploadFile, status
from pydantic import BaseModel

# Smallest valid 1x1 JPEG, returned by the mock /camera/picture endpoint.
_STUB_JPEG = bytes.fromhex(
    "ffd8ffe000104a46494600010100000100010000ffdb004300080606070605080707070909080a"
    "0c140d0c0b0b0c1912130f141d1a1f1e1d1a1c1c20242e2720222c231c1c2837292c30313434"
    "1f27393d38323c2e333432ffc0000b080001000101011100ffc4001f0000010501010101010100"
    "0000000000000000010203040506070809000a0bffc400b5100002010303020403050504040000"
    "017d01020300041105122131410613516107227114328191a1082342b1c11552d1f024336272"
    "82090a161718191a25262728292a3435363738393a434445464748494a535455565758595a63"
    "6465666768696a737475767778797a838485868788898a92939495969798999aa2a3a4a5a6a7"
    "a8a9aab2b3b4b5b6b7b8b9bac2c3c4c5c6c7c8c9cad2d3d4d5d6d7d8d9dae1e2e3e4e5e6e7e8"
    "e9eaf1f2f3f4f5f6f7f8f9faffda0008010100003f00fbfcffd9"
)

OPENTRONS_API_VERSION = "4"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class _RunCreate(BaseModel):
    protocolId: str | None = None
    runTimeParameterValues: dict[str, Any] | None = None
    labwareOffsets: list[dict[str, Any]] = []


class _ActionCreate(BaseModel):
    actionType: str


class _Body(BaseModel):
    data: Any


def create_app(*, run_duration: float = 1.0) -> FastAPI:
    """Build a fresh mock-robot app with isolated in-memory state.

    Args:
        run_duration: seconds between `play` and auto-transition to `succeeded`.
            Use 0.0 in tests so transitions resolve on the next event-loop tick.
    """
    protocols: dict[str, dict[str, Any]] = {}
    runs: dict[str, dict[str, Any]] = {}
    commands: dict[str, list[dict[str, Any]]] = {}

    app = FastAPI(title="capybara mock robot", version=OPENTRONS_API_VERSION)

    @app.post("/camera/picture")
    def camera_picture() -> Response:
        return Response(content=_STUB_JPEG, media_type="image/jpeg")

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "name": "capybara-mock",
            "api_version": OPENTRONS_API_VERSION,
            "fw_version": "mock",
            "robot_model": "OT-3 Standard",
        }

    @app.post("/protocols", status_code=status.HTTP_201_CREATED)
    async def upload_protocol(
        files: list[UploadFile],
        protocolKind: str = Form("standard"),
    ) -> dict[str, Any]:
        if not files:
            raise HTTPException(422, "no files supplied")
        pid = f"protocol-{uuid.uuid4().hex[:8]}"
        contents = [(f.filename or "protocol.py", await f.read()) for f in files]
        main_name, main_body = contents[0]

        commands, errors = await asyncio.to_thread(_simulate_protocol, main_body, main_name)
        analysis_id = f"analysis-{uuid.uuid4().hex[:8]}"
        analysis_result = "ok" if not errors else "not-ok"

        protocols[pid] = {
            "id": pid,
            "createdAt": _now(),
            "robotType": "OT-3 Standard",
            "protocolType": "python",
            "protocolKind": protocolKind,
            "metadata": {},
            "analyses": [],
            "analysisSummaries": [
                {"id": analysis_id, "status": "completed", "runTimeParameters": []}
            ],
            "files": [{"name": name, "role": "main"} for name, _ in contents],
            "_contents": {name: body for name, body in contents},
            "_commands": commands,
            "_analysis": {
                "id": analysis_id,
                "status": "completed",
                "result": analysis_result,
                "errors": errors,
                "commands": commands,
            },
        }
        return {"data": {k: v for k, v in protocols[pid].items() if not k.startswith("_")}}

    @app.get("/protocols/{protocol_id}/analyses/{analysis_id}")
    def get_analysis(protocol_id: str, analysis_id: str) -> dict[str, Any]:
        p = protocols.get(protocol_id)
        if p is None or p["_analysis"]["id"] != analysis_id:
            raise HTTPException(404, "analysis not found")
        return {"data": p["_analysis"]}

    @app.get("/protocols/{protocol_id}")
    def get_protocol(protocol_id: str) -> dict[str, Any]:
        p = protocols.get(protocol_id)
        if p is None:
            raise HTTPException(404, f"protocol {protocol_id} not found")
        return {"data": {k: v for k, v in p.items() if not k.startswith("_")}}

    @app.post("/runs", status_code=status.HTTP_201_CREATED)
    def create_run(body: _Body) -> dict[str, Any]:
        payload = _RunCreate.model_validate(body.data)
        if payload.protocolId and payload.protocolId not in protocols:
            raise HTTPException(404, f"protocol {payload.protocolId} not found")
        rid = f"run-{uuid.uuid4().hex[:8]}"
        # Pre-populate the run's commands as queued from the protocol's analysis.
        if payload.protocolId:
            base = protocols[payload.protocolId]["_commands"]
            commands[rid] = [{**c, "status": "queued"} for c in base]
        else:
            commands[rid] = []
        runs[rid] = {
            "id": rid,
            "createdAt": _now(),
            "status": "idle",
            "current": True,
            "protocolId": payload.protocolId,
            "startedAt": None,
            "completedAt": None,
            "errors": [],
            "actions": [],
            "pipettes": [],
            "modules": [],
            "labware": [],
            "liquids": [],
            "liquidClasses": [],
            "labwareOffsets": [],
            "runTimeParameters": [],
            "outputFileIds": [],
            "hasEverEnteredErrorRecovery": False,
        }
        # If the protocol analysis errored, surface those errors on the run too —
        # creating the run succeeds, but playing it will fail.
        if payload.protocolId:
            runs[rid]["errors"] = list(protocols[payload.protocolId]["_analysis"]["errors"])
        return {"data": runs[rid]}

    @app.get("/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, Any]:
        r = runs.get(run_id)
        if r is None:
            raise HTTPException(404, f"run {run_id} not found")
        return {"data": r}

    @app.post("/runs/{run_id}/actions", status_code=status.HTTP_201_CREATED)
    async def post_action(run_id: str, body: _Body) -> dict[str, Any]:
        r = runs.get(run_id)
        if r is None:
            raise HTTPException(404, f"run {run_id} not found")
        action = _ActionCreate.model_validate(body.data)
        aid = f"action-{uuid.uuid4().hex[:8]}"
        record = {"id": aid, "createdAt": _now(), "actionType": action.actionType}
        r["actions"].append(record)

        if action.actionType == "play":
            if r["status"] in {"succeeded", "failed", "stopped"}:
                raise HTTPException(409, f"run already {r['status']}")
            r["status"] = "running"
            r["startedAt"] = r["startedAt"] or _now()
            if r["errors"]:
                # Protocol analysis already errored; play just marks failed.
                asyncio.create_task(_fail_soon(run_id))
            else:
                asyncio.create_task(_play(run_id, run_duration))
        elif action.actionType == "pause":
            if r["status"] == "running":
                r["status"] = "paused"
        elif action.actionType == "stop":
            r["status"] = "stop-requested"
            asyncio.create_task(_stop_soon(run_id))
        return {"data": record}

    @app.get("/runs/{run_id}/commands")
    def list_commands(
        run_id: str,
        cursor: int = 0,
        pageLength: int = 20,
    ) -> dict[str, Any]:
        if run_id not in runs:
            raise HTTPException(404, f"run {run_id} not found")
        all_cmds = commands[run_id]
        page = all_cmds[cursor : cursor + pageLength]
        return {
            "data": page,
            "meta": {
                "cursor": cursor,
                "pageLength": len(page),
                "totalLength": len(all_cmds),
            },
            "links": {},
        }

    async def _play(run_id: str, total_duration: float) -> None:
        """Walk through the run's queued commands, transitioning each in turn."""
        r = runs[run_id]
        cmds = commands[run_id]
        per_cmd = total_duration / max(len(cmds), 1) if total_duration > 0 else 0.0
        for cmd in cmds:
            if runs[run_id]["status"] != "running":
                return  # paused, stopped, etc.
            cmd["status"] = "running"
            cmd["startedAt"] = _now()
            if per_cmd:
                await asyncio.sleep(per_cmd)
            cmd["status"] = "succeeded"
            cmd["completedAt"] = _now()
        r["status"] = "succeeded"
        r["completedAt"] = _now()
        r["current"] = False

    async def _fail_soon(run_id: str) -> None:
        await asyncio.sleep(0)
        r = runs.get(run_id)
        if r is not None:
            r["status"] = "failed"
            r["completedAt"] = _now()
            r["current"] = False

    async def _stop_soon(run_id: str) -> None:
        await asyncio.sleep(0)
        r = runs.get(run_id)
        if r is not None and r["status"] != "succeeded":
            r["status"] = "stopped"
            r["completedAt"] = _now()
            r["current"] = False

    return app


_COMMAND_TYPE_HINTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^Picking up tip"), "pickUpTip"),
    (re.compile(r"^Dropping tip"), "dropTip"),
    (re.compile(r"^Aspirating"), "aspirate"),
    (re.compile(r"^Dispensing"), "dispense"),
    (re.compile(r"^Moving"), "moveLabware"),
    (re.compile(r"^Loading"), "loadLabware"),
    (re.compile(r"^Blowing out"), "blowOut"),
    (re.compile(r"^Distributing"), "distribute"),
    (re.compile(r"^Transferring"), "transfer"),
    (re.compile(r"^Touching tip"), "touchTip"),
    (re.compile(r"^Mixing"), "mix"),
    (re.compile(r"^Pausing"), "waitForResume"),
    (re.compile(r"^Delaying"), "waitForDuration"),
    (re.compile(r"^Homing"), "home"),
)


def _command_type(text: str) -> str:
    for pat, name in _COMMAND_TYPE_HINTS:
        if pat.search(text):
            return name
    return "comment"


def _simulate_protocol(
    body: bytes, file_name: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Run the uploaded protocol through opentrons.simulate.

    Returns (commands, errors). On success, errors is empty. On a protocol
    engine failure, commands is empty and errors carries one entry per
    structured ErrorOccurrence raised by the simulator.
    """
    from opentrons.simulate import simulate
    from opentrons.util.entrypoint_util import ProtocolEngineExecuteError

    try:
        run_log, _bundle = simulate(io.StringIO(body.decode("utf-8")), file_name=file_name)
    except ProtocolEngineExecuteError as e:
        errors = [
            {
                "id": getattr(err, "id", uuid.uuid4().hex[:8]),
                "errorType": getattr(err, "errorType", "ProtocolEngineExecuteError"),
                "errorCode": getattr(err, "errorCode", "4000"),
                "detail": getattr(err, "detail", str(err)),
                "createdAt": _now(),
            }
            for err in (e.args[0] if e.args else [e])
        ]
        return [], errors
    except Exception as e:  # parse errors, ImportError, etc.
        return [], [
            {
                "id": uuid.uuid4().hex[:8],
                "errorType": type(e).__name__,
                "errorCode": "4001",
                "detail": str(e),
                "createdAt": _now(),
            }
        ]

    commands: list[dict[str, Any]] = []
    for i, entry in enumerate(run_log):
        payload = entry.get("payload", {})
        text = payload.get("text", "")
        params: dict[str, Any] = {"text": text}
        for k in ("volume", "rate"):
            if k in payload:
                params[k] = payload[k]
        commands.append(
            {
                "id": f"cmd-{i:04d}",
                "key": f"cmd-{i:04d}",
                "commandType": _command_type(text),
                "createdAt": _now(),
                "startedAt": None,
                "completedAt": None,
                "status": "queued",
                "params": params,
                "notes": [],
                "intent": "protocol",
            }
        )
    return commands, []


app = create_app()


def main() -> None:
    """CLI entry point. `capybara-mock-robot --port 31950 --duration 2.0`."""
    import argparse

    import uvicorn

    parser = argparse.ArgumentParser(description="Run the capybara mock Opentrons HTTP API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=31950)
    parser.add_argument(
        "--duration",
        type=float,
        default=1.0,
        help="Seconds between `play` action and auto-transition to succeeded.",
    )
    args = parser.parse_args()

    # Override the module-level app's run_duration by replacing it.
    global app  # noqa: PLW0603
    app = create_app(run_duration=args.duration)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
