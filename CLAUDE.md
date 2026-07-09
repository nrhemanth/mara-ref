# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this branch is

This is the `orchestrate` branch: it holds the orchestration layer that ties the
Opentrons OT-2 liquid handler, an IKA hotplate (serial), and (eventually) other
lab hardware together into one automated synthesis run, driven from a script on
the instrument PC. It's a much smaller slice of the wider Mara project — other
branches carry the experiment-specific protocol logic, config-driven deck setup,
notebooks, etc. Don't assume files referenced from other branches (e.g.
`modules/`, `config/*.yaml`, `hardware/ot2_actions.py`) exist here.

## Commands

```bash
# Install (editable) with uv — uv.lock is authoritative
uv sync

# or with plain pip
pip install -e .

# Run the mock Opentrons HTTP API locally (for development without real hardware)
mara-mock-robot                       # http://127.0.0.1:31950
mara-mock-robot --port 31951 --duration 2.0   # custom port / run-duration

# Run an orchestration script against the mock
ROBOT_URL=http://127.0.0.1:31950 python -m preruns.preflight_home protocols/home_ot2.py
ROBOT_URL=http://127.0.0.1:31950 python -m preruns.preflight_csv protocols/mara_perovskite_hardcode.py samples.csv
ROBOT_URL=http://127.0.0.1:31950 IKA_PORT=COM4 python -m preruns.preflight_films protocols/mara_perovskite_user_edit.py samples.csv

# Run the same against real hardware — just point ROBOT_URL at the robot
ROBOT_URL=http://<robot-ip>:31950 python -m preruns.preflight_films ...

# Simulate a protocol file locally (fast iteration on protocol logic, no robot/mock needed)
opentrons_simulate protocols/mara_perovskite_user_edit.py
```

There is no test suite yet (`pytest` is listed as a dev dependency in
`pyproject.toml` but no test files exist). There's also no lint/format command
configured — none of `ruff`, `black`, `flake8`, etc. are set up.

Scripts under `preruns/` are meant to be invoked with `python -m preruns.<name>`
from the repo root (not `python preruns/<name>.py`), so that `hardware` and
`mara` resolve as top-level imports.

## Architecture

The system is split into four layers that run in **different processes, and
sometimes different machines**. Understanding which layer a piece of code
belongs to — and what can and can't cross between them — is the main thing to
get right here.

### 1. `src/mara/` — the instrument-PC client package (installed as `mara`)

- **`runtime.py`** — `CapyClient`, a hand-written `httpx` wrapper around the
  real Opentrons HTTP API (protocol upload, run creation, play/pause/stop
  actions, command/status polling). This is the only way this codebase talks
  to a robot — there is no other transport. `opentrons-openapi.json` at the
  repo root (if present) is the authoritative spec for what the real API
  returns; `CapyClient`'s Pydantic models (`_Loose` base, `extra="allow"`)
  intentionally only pin the fields it uses.
- **`mock_robot.py`** — a stateful, in-memory FastAPI implementation of that
  same API surface (`/health`, `/protocols`, `/runs`, `/runs/{id}/actions`,
  `/runs/{id}/commands`, `/camera/picture`). On protocol upload it actually
  runs the file through `opentrons.simulate` to generate a realistic command
  list and catch analysis errors, then fakes real-time command execution on a
  timer after `play`. This is what `mara-mock-robot` serves, and what
  `CapyClient(client=TestClient(app))` can wrap directly for in-process tests.
- **`preflight.py`** — `confirm_deck_state()`: snap a picture from the robot's
  camera, save it locally, and block on a human "proceed? \[y/N]" prompt
  before anything runs. Every orchestration script calls this before `play`.
- **`utils.py`** — small stateless-ish helpers: `deck_snapshot()` (lists
  loaded labware from a live `ProtocolContext`) and a background
  `TimerThread`/`add_material()` pair for tracking wall-clock timers.

### 2. `hardware/` — direct hardware drivers, independent of Opentrons

Each file talks to one physical device over its own transport, with no
knowledge of protocols, samples, or experiments:
- `hp_rct5.py` — `IkaRct5`, serial (RS232 NAMUR protocol) control of an IKA
  RCT 5 hotplate stirrer: set/read temperature and stirring speed, start/stop.
- `dobot_e6.py` — `DobotE6`, TCP control (two plaintext sockets: dashboard +
  motion) of a Dobot E6 arm.
- `kamome.py` — currently empty; placeholder for another device driver.

### 3. `protocols/` — Opentrons protocol files

Plain Python files shaped the way Opentrons expects (`requirements = {...}`
plus `def run(protocol): ...`). **These execute on the OT-2's own onboard
robot server**, not in this repo's Python environment — `CapyClient` uploads
the file's bytes over HTTP and the robot runs it. This has two consequences
that matter for anything you write here:

- **No imports from this repo.** The onboard Python does not have `mara`,
  `hardware`, or anything else from this codebase installed. Protocol files
  must be fully self-contained (stdlib + `opentrons` only). If a protocol
  needs a small utility (e.g. a background timer), inline it rather than
  importing it.
- **The only channel back to the instrument PC is the run's command list.**
  A protocol can't push a message to the orchestration script directly (no
  callback, no shared process). What it *can* do is call `protocol.comment("some
  marker text")`, which becomes a `comment`-type command in the run, visible
  via `CapyClient.list_commands(run_id)`. `preruns/preflight_films.py` uses
  exactly this: `mara_perovskite_user_edit.py`'s `drop_cast_single` emits
  `protocol.comment(f"TIMER_START sample={id} anneal_min={m}")` right after
  each sample's drop is dispensed, and the orchestration script polls for that
  marker and computes each sample's pickup-ready time itself (marker's
  timestamp + `anneal_min`) — the robot never "reports" readiness, the client
  derives it.
- **Real vs. mock command shape differs.** A real `protocol.comment()` shows
  up with `params.message`. The mock derives commands from `opentrons.simulate`'s
  text run log and stores `params.text` instead. Code reading command params
  (see `track_pickup_timers` in `preflight_films.py`) checks both keys.

### 4. `preruns/` — orchestration entry points (run on the instrument PC)

Each script in here is a `main(...)` driving one full workflow end-to-end,
following the same shape: read `ROBOT_URL` from the environment, open a
`CapyClient`, run `confirm_deck_state()`, upload + create + play a run, then
poll `stream_status()` until a terminal status
(`stopped`/`failed`/`succeeded`, see `TERMINAL_STATUSES`). They differ in what
they layer on top:
- `preflight_home.py` — the minimal version (upload, preflight, play, wait).
- `preflight_csv.py` — also attaches a CSV of run parameters alongside the
  protocol upload (`upload_protocol_with_csv`).
- `preflight_films.py` — the fullest version: reads a `samples.csv`
  (`sample_id`, `temperature`, `anneal_min` columns), starts the IKA hotplate
  over serial at the (single, shared) temperature *before* playing the run,
  then after the run finishes keeps polling for `TIMER_START` markers and
  reports each sample's pickup time as it comes due (see layer 3 above for
  why this is polling rather than a push).
- `run_perovskite_json.py` — an older inline (non-`main()`) script; references
  `modules/mara_perovskite.py` and `custom_labware/single_bundle_6_channel.json`,
  neither of which exists on this branch. Treat it as stale/reference-only
  until those paths are ported over.

### Known inconsistency

`src/mara/preflight.py` imports via `from src.mara.runtime import CapyClient`,
while every other consumer uses `from mara.runtime import ...` (the installed
package). Both resolve to the same file when run from the repo root, but as
two distinct module objects — worth normalizing to one form if you're touching
that file.
