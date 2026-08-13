"""Orchestration entry point: scan a well-plate range with the Tsuru gantry,
photographing each well with the USB camera and saving each shot as
"{well}_{ID}.jpg" (e.g. "A1_FOKYMT.jpg").

Tsuru replacement for preruns/pl_scan.py's Kamome-based version. Doesn't
touch the OT-2 at all - drives the Tsuru gantry (hardware/tsuru.py) directly,
on its own serial connection, plus a USB webcam via OpenCV (opened directly
by device index, so the Windows Camera app doesn't need to be running).

Unlike the Kamome version, well iteration doesn't need to be hand-rolled
here - Tsuru.scan_plate() already sweeps a plate's well range itself and
calls back per well once the gantry has arrived and settled.

Sample IDs come from an optional CSV with "well" and "ID" (or "sample_id")
columns - same shape as protocols/2D_mapbi3_perovskite_test.py's BATCH_CSV.
Wells with no matching row are saved as just "{well}.jpg".

Usage:
    python -m characterize.tsuru_camera_scan Thinfilm_20 A1 D5 results/ samples.csv
    TSURU_PORT=COM5 CAMERA_INDEX=1 python -m characterize.tsuru_camera_scan Thinfilm_20 A1 D5

CAMERA_ZOOM (optional) sets cv2.CAP_PROP_ZOOM after opening the camera - only
takes effect if the camera exposes a UVC zoom control; fixed-lens webcams
have no optical zoom and silently ignore it (a warning is printed either
way, since there's no portable way to ask OpenCV for the valid range).
"""

from __future__ import annotations

import csv
import os
import sys
import threading
import time
from pathlib import Path

import cv2

from hardware.tsuru import PORT as DEFAULT_PORT
from tsuru_sdk import Mode, Tsuru
from tsuru_sdk.config import PLATE_TYPES

DEFAULT_CAMERA_INDEX = 0
WARMUP_SECONDS = 1.0  # let the grabber thread get a first frame + exposure settle before scanning

# Tsuru.scan_plate fires each move_well the instant the previous one reports
# "At well", with no settle time - the serpentine sweep reverses X direction
# every other row, and back-to-back reversals were observed to make the
# gantry drift (see characterize/tsuru_pl_grid_scan.py, where this was first
# hit at tighter spacing). Dwell after each well before the next move_well
# goes out. Override via env var to tune without editing code.
SETTLE_SECONDS = float(os.environ.get("SETTLE_SECONDS", "0.4"))

# Windows backends to try in order - DSHOW can refuse to open some USB cameras
# by plain index ("backend is generally available but can't be used to
# capture by index") even though the same device works fine under MSMF, or
# vice versa depending on the camera's drivers. Try both before giving up.
_CANDIDATE_BACKENDS = (cv2.CAP_MSMF, cv2.CAP_DSHOW, cv2.CAP_ANY)


def open_camera(camera_index: int) -> cv2.VideoCapture:
    for backend in _CANDIDATE_BACKENDS:
        camera = cv2.VideoCapture(camera_index, backend)
        if camera.isOpened():
            return camera
        camera.release()
    raise RuntimeError(
        f"Could not open camera at index {camera_index} with any backend "
        f"(tried MSMF, DSHOW, ANY) - check CAMERA_INDEX and that no other "
        f"app (e.g. Windows Camera) is holding the device open."
    )


def apply_zoom(camera: cv2.VideoCapture, zoom: float) -> None:
    """Best-effort CAP_PROP_ZOOM set; prints whether the camera reflected it back."""
    before = camera.get(cv2.CAP_PROP_ZOOM)
    camera.set(cv2.CAP_PROP_ZOOM, zoom)
    after = camera.get(cv2.CAP_PROP_ZOOM)
    if after == zoom:
        print(f"Zoom set to {after}")
    else:
        print(
            f"Warning: requested zoom={zoom}, camera reports {after} "
            f"(was {before}) - this camera may not support a zoom control, "
            f"or clamps to a different range than requested."
        )


def load_well_ids(csv_path: Path) -> dict[str, str]:
    """film-plate well -> sample ID, keyed off a CSV's well + ID columns.

    Prefers "film_well" over "well" - in the BATCH_CSV shape (see
    protocols/2D_mapbi3_perovskite_test.py), "well" is the shared precursor
    source reservoir (e.g. only A4/B4, reused across many samples) while
    "film_well" is each sample's unique destination position on the plate
    this script actually photographs. Keying off "well" would collapse
    multiple samples onto one filename.
    """
    with csv_path.open(newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        well_col = "film_well" if "film_well" in fieldnames else "well"
        id_col = "ID" if "ID" in fieldnames else "sample_id"
        return {row[well_col].strip().upper(): row[id_col].strip() for row in reader}


class LiveFrameGrabber:
    """Continuously reads frames from `camera` on a background thread, so a
    capture always gets whatever's most current.

    gantry.move_to_well() blocks the main thread on a synchronous serial
    read for the whole physical move - camera.read() never gets called
    during that window, so frames pile up unread in the driver's buffer. A
    fixed post-arrival "flush for N seconds" can't reliably outrun that
    backlog (worst case is the very first well, which also eats the
    Tsuru connection's ~2s reset delay before any move even starts) - it's
    guessing a constant against an unknown backlog depth. Reading
    continuously in the background sidesteps the problem entirely: there's
    never a backlog to catch up on, because something is always draining
    the camera even while the main thread is stuck waiting on the gantry.
    """

    def __init__(self, camera: cv2.VideoCapture):
        self._camera = camera
        self._lock = threading.Lock()
        self._frame = None
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while self._running:
            ok, frame = self._camera.read()
            if ok:
                with self._lock:
                    self._frame = frame

    def latest(self):
        with self._lock:
            if self._frame is None:
                raise RuntimeError("No frame captured yet")
            return self._frame.copy()

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)


def main(plate_type: str, start_well: str, end_well: str, out_dir: Path, csv_path: Path | None) -> int:
    if plate_type not in PLATE_TYPES:
        available = ", ".join(PLATE_TYPES.keys())
        raise ValueError(f"Unknown plate type '{plate_type}'. Available: {available}")

    tsuru_port = os.environ.get("TSURU_PORT", DEFAULT_PORT)
    camera_index = int(os.environ.get("CAMERA_INDEX", DEFAULT_CAMERA_INDEX))
    out_dir.mkdir(parents=True, exist_ok=True)
    well_ids = load_well_ids(csv_path) if csv_path else {}
    captured: list[Path] = []

    camera = open_camera(camera_index)
    grabber = LiveFrameGrabber(camera)
    grabber.start()

    try:
        zoom = os.environ.get("CAMERA_ZOOM")
        if zoom is not None:
            apply_zoom(camera, float(zoom))

        time.sleep(WARMUP_SECONDS)

        def on_well(well: str) -> None:
            sample_id = well_ids.get(well.upper())
            frame = grabber.latest()
            name = f"{well}_{sample_id}" if sample_id else well
            out_path = out_dir / f"{name}.jpg"
            cv2.imwrite(str(out_path), frame)
            captured.append(out_path)
            print(f"[{well}] saved {out_path.name}")
            time.sleep(SETTLE_SECONDS)

        with Tsuru(tsuru_port) as gantry:
            gantry.scan_plate(Mode.CAMERA, plate_type, start_well, end_well, on_well=on_well)
            gantry.home()
    finally:
        grabber.stop()
        camera.release()

    print(f"Done. {len(captured)} images written to {out_dir}")
    return 0


if __name__ == "__main__":
    plate_type = sys.argv[1]
    start_well = sys.argv[2]
    end_well = sys.argv[3]
    out_dir = Path(sys.argv[4]) if len(sys.argv) > 4 else Path("camera_scan_results")
    csv_path = Path(sys.argv[5]) if len(sys.argv) > 5 else None

    sys.exit(main(plate_type, start_well, end_well, out_dir, csv_path))
