from datetime import datetime, timedelta
import time
import threading

requirements = {"robotType": "OT-2", "apiLevel": "2.27"}


# ---------------------------------------------------------------------------
# Pickup timer -- inlined here (rather than imported from mara.utils) so this
# protocol file has no dependency on the rest of the repo being installed.
# Only tracks wall-clock time in this local Python process, so it's only
# meaningful when running via opentrons_execute with a terminal attached --
# not when uploaded through the Opentrons App.
# ---------------------------------------------------------------------------
active_timers = {}

class TimerThread(threading.Thread):
    def __init__(self, material_id, duration_min):
        super().__init__()
        self.material_id = material_id
        self.duration = timedelta(minutes=duration_min)
        self.start_time = datetime.now()
        self.end_time = self.start_time + self.duration

    def run(self):
        time.sleep(self.duration.total_seconds())
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Material {self.material_id} is done!")

def add_material(material_id, duration_min):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Timer started for {material_id} ({duration_min} min)")
    thread = TimerThread(material_id, duration_min)
    active_timers[material_id] = thread
    thread.start()


# ---------------------------------------------------------------------------
# Timer-only smoke test: no drop-cast movement, no labware/pipette loads --
# just home() plus 16 pickup timers fired one at a time, 20s apart, so the
# TIMER_START marker/polling machinery (preruns/preflight_films.py) can be
# exercised end-to-end without touching real deck hardware.
# ---------------------------------------------------------------------------
NUM_SAMPLES = 16
TIMER_SPACING_SECONDS = 3
ANNEAL_MIN = 1  # placeholder anneal time for every fake sample in this test

def run(protocol):
    protocol.home()

    for sample_id in range(1, NUM_SAMPLES + 1):
        if sample_id > 1:
            protocol.delay(seconds=TIMER_SPACING_SECONDS)
        add_material(sample_id, ANNEAL_MIN)
        protocol.comment(f"TIMER_START sample={sample_id}")