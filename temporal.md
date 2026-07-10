# How to test the Temporal orchestration

## Against the mock (no real hardware)

Open 4 terminals from the repo root.

**Terminal 1 — Temporal dev server** (with persistence, so state survives a
restart; keep the Web UI so you can watch it):

```powershell
mkdir .temporal   # first time only -- the CLI won't create the dir itself
temporal server start-dev --db-filename .temporal/dev.db
```

Leave this running. Web UI: http://localhost:8233

**Terminal 2 — mock OT-2 robot:**

```powershell
uv run mara-mock-robot
```

Serves at http://127.0.0.1:31950

**Terminal 3 — the Temporal worker** (must run from the repo root so
`hardware`/`mara` resolve):

```powershell
uv run python -m mara.temporal.worker
```

You should see `worker listening on task queue 'mara-films' @ localhost:7233`.

**Terminal 4 — kick off a run.** You need a `samples.csv` (see below), then:

```powershell
$env:ROBOT_URL = "http://127.0.0.1:31950"
uv run python -m preruns.preflight_films_temporal protocols/mara_perovskite_user_edit.py samples.csv
```

It'll prompt `Proceed with run? [y/N]` after snapping a (mock) deck photo,
then print the workflow ID and a Web UI link — open that to watch the
heater/upload/run/marker-polling activities complete live.

**Catch:** `start_heater_activity` calls the real IKA driver
(`hardware/hp_rct5.py`), so without a heater physically on `IKA_PORT`
(default `COM4`) it'll fail and retry 5 times, then the workflow fails —
same hardware dependency the original `preflight_films.py` always had. Set
`$env:IKA_PORT` to a real port if you have the hotplate connected;
otherwise this step is expected to fail in the Web UI, and that's not a bug.

**To test the durability property** (the whole reason for this): once a
`TIMER_START` marker has fired (visible in the Web UI event history) but
before its notify fires, Ctrl+C the worker in Terminal 3, restart it, and
watch the same workflow pick back up and still notify on time — nothing is
lost.

## Against the real robot + heater

Same four terminals, except:

- Skip Terminal 2 (no mock robot needed).
- Point at the real hardware instead of the mock:

```powershell
$env:ROBOT_URL = "http://192.168.1.102:31950"   # your OT-2's address
$env:IKA_PORT = "COM4"                          # your hotplate's COM port
uv run python -m preruns.preflight_films_temporal protocols/mara_perovskite_user_edit.py samples.csv
```

Terminals 1 and 3 (Temporal server, worker) don't change — they run locally
on the instrument PC regardless of where the OT-2 is.

## samples.csv

Columns: `sample_id, temperature, anneal_min`. `temperature` must be the
same value on every row (one physical hotplate for the whole batch);
`anneal_min` varies per sample. Minimal example for a quick mock test:

```csv
sample_id,temperature,anneal_min
1,80,1
2,80,2
```

<!--
TODO: the rows below look like a fragment of a real sample list pasted in
earlier (no header, row 30 has an extra field: `30,5,0,150.0,`) -- clean up
or replace with a real samples.csv before using for an actual run.

28,5.0,60.0,
29,5.0,105.0,
30,5,0,150.0,
31,30.0,60.0,
32,30.0,105.0,
33,30.0,150.0,
34,60.0,60.0,
35,60.0,105.0,
36,60.0,150.0,
-->
