Terminal 1 — Temporal dev server (with persistence, and this time keep the Web UI so you can watch it):


temporal server start-dev --db-filename .temporal/dev.db
Leave this running. Web UI: http://localhost:8233

Terminal 2 — mock OT-2 robot (no real hardware needed):


uv run mara-mock-robot
Serves at http://127.0.0.1:31950

Terminal 3 — the Temporal worker (must run from repo root so hardware/mara resolve):


uv run python -m mara.temporal.worker
You should see worker listening on task queue 'mara-films' @ localhost:7233.

Terminal 4 — kick off a run. You need a samples.csv — none exists in the repo yet, so make one, e.g.:


sample_id,temperature,anneal_min
1,80,1
2,80,2
(short anneal_min values so you don't wait long)

Then:


$env:ROBOT_URL = "http://127.0.0.1:31950"
uv run python -m preruns.preflight_films_temporal protocols/mara_perovskite_user_edit.py samples.csv
It'll prompt Proceed with run? [y/N] after snapping a (mock) deck photo, then print the workflow ID and a Web UI link — open that to watch the heater/upload/run/marker-polling activities complete live.

One catch: start_heater_activity calls your real IKA driver (hardware/hp_rct5.py), so without a heater physically on IKA_PORT (default COM4) it'll fail and retry 5 times, then the workflow fails — same hardware dependency the original preflight_films.py always had. Set $env:IKA_PORT to a real port if you have the hotplate connected; otherwise this step is expected to fail in the Web UI, and that's not a bug.

To actually test the durability property (the whole reason for this): once a TIMER_START marker has fired (visible in the Web UI event history) but before its notify fires, Ctrl+C the worker in Terminal 3, restart it, and watch the same workflow pick back up and still notify on time — nothing is lost.


28,5.0,60.0,
29,5.0,105.0,
30,5,0,150.0,
31,30.0,60.0,
32,30.0,105.0,
33,30.0,150.0,
34,60.0,60.0,
35,60.0,105.0,
36,60.0,150.0,
