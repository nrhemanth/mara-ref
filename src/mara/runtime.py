"""Instrument-PC client for the Opentrons HTTP API.

Hand-written httpx wrapper covering only the endpoints capybara drives:
health, protocol upload, run lifecycle, action dispatch, and command streaming.

The Opentrons HTTP API spec (opentrons-openapi.json at repo root) is the
authoritative reference for request/response shapes; the Pydantic models here
mirror the relevant subset and ignore fields we don't use.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Generic, Literal, TypeVar

import httpx
from pydantic import BaseModel, ConfigDict, Field

OPENTRONS_API_VERSION = "4"
RunStatus = Literal[
    "idle",
    "running",
    "paused",
    "blocked-by-open-door",
    "stop-requested",
    "finishing",
    "awaiting-recovery",
    "awaiting-recovery-paused",
    "awaiting-recovery-blocked-by-open-door",
    "stopped",
    "failed",
    "succeeded",
]
RunActionType = Literal[
    "play",
    "pause",
    "stop",
    "resume-from-recovery",
    "resume-from-recovery-assuming-false-positive",
]
TERMINAL_STATUSES: frozenset[str] = frozenset({"stopped", "failed", "succeeded"})


class _Loose(BaseModel):
    """Base model that tolerates extra fields — we only pin the ones we use."""

    model_config = ConfigDict(extra="allow")


class Protocol(_Loose):
    id: str
    createdAt: str
    robotType: str
    protocolType: str
    analysisSummaries: list[dict[str, Any]] = Field(default_factory=list)


class Run(_Loose):
    id: str
    createdAt: str
    status: RunStatus
    current: bool
    protocolId: str | None = None
    startedAt: str | None = None
    completedAt: str | None = None
    errors: list[dict[str, Any]] = Field(default_factory=list)


class RunAction(_Loose):
    id: str
    createdAt: str
    actionType: RunActionType


class Command(_Loose):
    id: str
    commandType: str
    status: str
    createdAt: str


T = TypeVar("T", bound=BaseModel)


class Envelope(BaseModel, Generic[T]):
    data: T


class ListEnvelope(BaseModel, Generic[T]):
    data: list[T]
    meta: dict[str, Any] = Field(default_factory=dict)
    links: dict[str, Any] = Field(default_factory=dict)


class CapyError(RuntimeError):
    """Raised for non-2xx responses from the OT HTTP API."""

    def __init__(self, response: httpx.Response):
        self.status_code = response.status_code
        try:
            self.payload = response.json()
        except ValueError:
            self.payload = response.text
        super().__init__(f"{response.request.method} {response.request.url} -> {response.status_code}: {self.payload}")


class CapyClient:
    """Minimal Opentrons HTTP API client for protocol upload + run lifecycle.

    Usage:
        with CapyClient("http://capy.local:31950") as c:
            c.health()
            p = c.upload_protocol(Path("protocol.py"))
            r = c.create_run(p.id, {"x": 0.3})
            c.run_action(r.id, "play")
            for state in c.stream_status(r.id):
                print(state.status)
                if state.status in TERMINAL_STATUSES:
                    break
    """

    def __init__(
        self,
        base_url: str | None = None,
        *,
        client: httpx.Client | None = None,
        timeout: float = 30.0,
        api_version: str = OPENTRONS_API_VERSION,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        """Either pass `base_url` (we build the client) or `client=` (you do).

        Passing a pre-built client is the seam for tests: a
        `starlette.testclient.TestClient(app)` is a sync httpx.Client subclass
        that bridges to ASGI in-process, so it slots in here directly.
        """
        if client is not None:
            self._client = client
            client.headers.setdefault("opentrons-version", api_version)
        else:
            if base_url is None:
                raise TypeError("CapyClient requires either base_url or client")
            self._client = httpx.Client(
                base_url=base_url.rstrip("/"),
                timeout=timeout,
                headers={"opentrons-version": api_version},
                transport=transport,
            )

    def __enter__(self) -> CapyClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    # --- requests ------------------------------------------------------

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        r = self._client.request(method, path, **kwargs)
        if r.status_code >= 400:
            raise CapyError(r)
        return r

    # --- endpoints -----------------------------------------------------

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health").json()

    def upload_protocol(self, path: Path, *, protocol_kind: str = "standard") -> Protocol:
        """Upload a protocol file. Returns immediately; analysis runs server-side."""
        with path.open("rb") as fh:
            r = self._request(
                "POST",
                "/protocols",
                files={"files": (path.name, fh, "text/x-python")},
                data={"protocolKind": protocol_kind},
            )
        return Envelope[Protocol].model_validate(r.json()).data
    
    def upload_protocol_with_csv(
        self,
        protocol_path: Path,
        csv_path: Path,
        *,
        protocol_kind: str = "standard",
    ) -> Protocol:
        """Upload a protocol + CSV together in one request."""
        with protocol_path.open("rb") as protocol_fh, csv_path.open("rb") as csv_fh:
            r = self._request(
                "POST",
                "/protocols",
                files=[
                    ("files", (protocol_path.name, protocol_fh, "text/x-python")),
                    ("files", (csv_path.name, csv_fh, "text/csv")),
                ],
                data={"protocolKind": protocol_kind},
            )

        return Envelope[Protocol].model_validate(r.json()).data

    def get_protocol(self, protocol_id: str) -> Protocol:
        r = self._request("GET", f"/protocols/{protocol_id}")
        return Envelope[Protocol].model_validate(r.json()).data

    def create_run(
        self,
        protocol_id: str,
        run_time_parameters: dict[str, Any] | None = None,
    ) -> Run:
        body: dict[str, Any] = {"data": {"protocolId": protocol_id}}
        if run_time_parameters:
            body["data"]["runTimeParameterValues"] = run_time_parameters
        r = self._request("POST", "/runs", json=body)
        return Envelope[Run].model_validate(r.json()).data

    def get_run(self, run_id: str) -> Run:
        r = self._request("GET", f"/runs/{run_id}")
        return Envelope[Run].model_validate(r.json()).data

    def run_action(self, run_id: str, action: RunActionType) -> RunAction:
        body = {"data": {"actionType": action}}
        r = self._request("POST", f"/runs/{run_id}/actions", json=body)
        return Envelope[RunAction].model_validate(r.json()).data

    def take_picture(self) -> bytes:
        """Capture a still image from the robot's onboard camera. Returns JPEG bytes."""
        r = self._request("POST", "/camera/picture")
        return r.content

    def list_commands(
        self,
        run_id: str,
        *,
        cursor: int | None = None,
        page_length: int | None = None,
    ) -> ListEnvelope[Command]:
        params: dict[str, Any] = {}
        if cursor is not None:
            params["cursor"] = cursor
        if page_length is not None:
            params["pageLength"] = page_length
        r = self._request("GET", f"/runs/{run_id}/commands", params=params)
        return ListEnvelope[Command].model_validate(r.json())

    # --- helpers -------------------------------------------------------

    def stream_status(
        self,
        run_id: str,
        *,
        poll_interval: float = 1.0,
    ) -> Iterator[Run]:
        """Yield Run snapshots until a terminal status. Caller decides when to stop."""
        last: str | None = None
        while True:
            run = self.get_run(run_id)
            if run.status != last:
                yield run
                last = run.status
            if run.status in TERMINAL_STATUSES:
                return
            time.sleep(poll_interval)
