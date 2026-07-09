# Mara — orchestration branch

Orchestration layer for automated materials synthesis: an Opentrons OT-2
liquid handler, an IKA hotplate (serial), and (eventually) other lab hardware,
driven end-to-end from a script running on the instrument PC.

This branch holds just that orchestration slice of the wider Mara project —
the client package, hardware drivers, Opentrons protocol files, and the
scripts that glue them together. See `CLAUDE.md` for the full architecture
write-up (how the pieces talk to each other, and what can/can't cross between
them).

## Install

```bash
uv sync
# or: pip install -e .
```

## Quick start (no real hardware needed)

Run the mock Opentrons HTTP API locally:

```bash
mara-mock-robot                          # serves http://127.0.0.1:31950
mara-mock-robot --port 31951 --duration 2.0
```

Point any orchestration script at it and run a protocol end-to-end:

```bash
ROBOT_URL=http://127.0.0.1:31950 python -m preruns.preflight_home protocols/home_ot2.py
```

## Running against real hardware

```bash
ROBOT_URL=http://<robot-ip>:31950 python -m preruns.preflight_csv \
    protocols/mara_perovskite_hardcode.py samples.csv

ROBOT_URL=http://<robot-ip>:31950 IKA_PORT=COM4 python -m preruns.preflight_films \
    protocols/mara_perovskite_user_edit.py samples.csv
```

`preflight_films.py` is the fullest workflow: it reads `samples.csv`
(`sample_id`, `temperature`, `anneal_min`), starts the IKA hotplate over
serial, plays the protocol, and then reports each sample's pickup time as it
comes due by polling the run's command list.

Run scripts with `python -m preruns.<name>` from the repo root, not
`python preruns/<name>.py` — module invocation is what puts the repo root on
`sys.path` so `hardware`/`mara` resolve correctly.

## Iterating on a protocol file without a robot or mock

```bash
opentrons_simulate protocols/mara_perovskite_user_edit.py
```

## Layout

- `src/mara/` — the instrument-PC client package: `runtime.py` (`CapyClient`,
  the Opentrons HTTP API wrapper), `mock_robot.py` (FastAPI mock of that same
  API for local dev), `preflight.py` (camera-snapshot + human-confirm gate),
  `utils.py` (misc helpers).
- `hardware/` — direct hardware drivers (IKA hotplate, Dobot arm, ...),
  independent of Opentrons.
- `protocols/` — Opentrons protocol files, uploaded to and executed by the
  OT-2's own onboard robot server.
- `preruns/` — orchestration entry points that tie it all together.

See `CLAUDE.md` for how these layers actually communicate (and their limits —
protocol files can't import anything from this repo, for instance).
