"""Diagnostic: isolate whether characterize/tsuru_pl_grid_scan.py's reported
X drift is (a) mechanical backlash - a fixed, repeatable offset every time
the gantry approaches a point from a given X direction - or (b) actual lost
stepper steps (stall) - error that grows across repeated moves and never
resets. Doesn't fix anything itself; the two causes need different fixes
(backlash is correctable in software with a compensating overshoot-then-
return move, stall is a firmware/mechanical problem no amount of Python-side
settling or reordering can correct), so this exists to tell them apart
before committing to one.

Uses Mode.CAMERA rather than PL: CAMERA_DELTA is (0, 0) (PLATE_TYPES is
calibrated directly against the camera - see tsuru_sdk/config.py), so there's
no probe-delta algebra to second-guess, and results are visual (a webcam
frame) instead of a spectrum, so drift is obvious at a glance with no
analysis step. The firmware is fully open-loop (no limit switches or
encoders - see Tsuru_Firmware.ino) and "home" only returns to logical
step-position (0, 0), not a physical reference, so there's no way to ask the
hardware "where are you really" - a camera frame is the only ground truth
available without physically instrumenting the rig.

For one well, captures repeated back-to-back:
  - baseline_N.jpg - direct move_to_well straight to the real well's center,
    with a home() round-trip before each one to force a fresh approach
    (not just holding position). This is "ground truth", entirely bypassing
    the grid scratch plate machinery.
  - grid_N_<point>.jpg - a full 3x3 grid sweep of `well` (same nested-
    serpentine path tsuru_pl_grid_scan.py uses: 1>2>3>6>5>4>7>8>9), all 9
    points, repeated for N passes with a home() round-trip between passes.

How to read the results:
  - Compare grid_1_5.jpg (grid path's point 5, the well center) against
    baseline_1.jpg (direct move to the same real center). A consistent
    offset between them, present from pass 1 and unchanged in later passes,
    points to backlash on the grid's internal B2 approach direction (point 5
    is always approached moving -X - see tsuru_pl_grid_scan.py's docstring).
  - Compare grid_1_5.jpg against grid_N_5.jpg (same point, later passes). If
    that offset grows pass over pass, that's stepper stall/lost steps, not
    backlash - it accumulates because nothing ever re-references true
    position.

Usage:
    python -m characterize.tsuru_grid_drift_diagnostic Thinfilm_20 A1 5 results/
    TSURU_PORT=COM5 CAMERA_INDEX=1 python -m characterize.tsuru_grid_drift_diagnostic Thinfilm_20 A1 5
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import cv2

from characterize.tsuru_camera_scan import LiveFrameGrabber, open_camera
from characterize.tsuru_pl_grid_scan import GRID_COL_DIST, GRID_KEY, GRID_POINT_LABEL, GRID_ROW_DIST
from hardware.tsuru import PORT as DEFAULT_PORT
from tsuru_sdk import Mode, Tsuru
from tsuru_sdk.config import CAMERA_DELTA, PLATE_TYPES, PlateType
from tsuru_sdk.tsuru import _well_row_col

DEFAULT_CAMERA_INDEX = 0
WARMUP_SECONDS = 1.0
SETTLE_SECONDS = float(os.environ.get("SETTLE_SECONDS", "0.4"))


def register_grid_plate_type_camera(plate_type: str, well: str) -> None:
    """Same construction as tsuru_pl_grid_scan.register_grid_plate_type, but
    keyed to CAMERA_DELTA instead of PL_DELTA so this diagnostic exercises
    the identical grid geometry under the probe-free, already-zero-delta
    camera mode."""
    plate = PLATE_TYPES[plate_type]
    well_row, well_col = _well_row_col(well)

    center_x = (plate.offset_x + CAMERA_DELTA.dx) + (well_col - 1) * plate.col_dist
    center_y = (plate.offset_y + CAMERA_DELTA.dy) + (plate.rows - well_row) * plate.row_dist

    PLATE_TYPES[GRID_KEY] = PlateType(
        offset_x=center_x - CAMERA_DELTA.dx - GRID_COL_DIST,
        offset_y=center_y - CAMERA_DELTA.dy - GRID_ROW_DIST,
        col_dist=GRID_COL_DIST,
        row_dist=GRID_ROW_DIST,
        rows=3,
        cols=3,
    )


def main(plate_type: str, well: str, passes: int, out_dir: Path) -> int:
    if plate_type not in PLATE_TYPES:
        available = ", ".join(PLATE_TYPES.keys())
        raise ValueError(f"Unknown plate type '{plate_type}'. Available: {available}")

    tsuru_port = os.environ.get("TSURU_PORT", DEFAULT_PORT)
    camera_index = int(os.environ.get("CAMERA_INDEX", DEFAULT_CAMERA_INDEX))
    out_dir.mkdir(parents=True, exist_ok=True)

    camera = open_camera(camera_index)
    grabber = LiveFrameGrabber(camera)
    grabber.start()

    def capture(name: str) -> None:
        time.sleep(SETTLE_SECONDS)
        frame = grabber.latest()
        cv2.imwrite(str(out_dir / f"{name}.jpg"), frame)
        print(f"saved {name}.jpg")

    try:
        time.sleep(WARMUP_SECONDS)

        with Tsuru(tsuru_port) as gantry:
            print(f"Baseline: {passes} fresh direct approaches to {well}'s center...")
            for p in range(1, passes + 1):
                gantry.home()
                gantry.move_to_well(Mode.CAMERA, plate_type, well)
                capture(f"baseline_{p}")

            print(f"Grid: {passes} back-to-back 3x3 sweeps of {well}'s grid...")
            register_grid_plate_type_camera(plate_type, well)
            for p in range(1, passes + 1):
                gantry.home()

                def on_grid_point(grid_well: str, p=p) -> None:
                    point = GRID_POINT_LABEL[grid_well]
                    capture(f"grid_{p}_{point}")

                gantry.scan_plate(Mode.CAMERA, GRID_KEY, "A1", "C3", on_well=on_grid_point)

            gantry.home()
    finally:
        grabber.stop()
        camera.release()

    print(
        f"\nDone. {passes} baseline + {passes} grid passes written to {out_dir}.\n"
        f"Compare grid_1_5.jpg to baseline_1.jpg -> fixed offset there = backlash.\n"
        f"Compare grid_1_5.jpg to grid_{passes}_5.jpg -> growing offset there = lost steps/stall."
    )
    return 0


if __name__ == "__main__":
    plate_type = sys.argv[1]
    well = sys.argv[2]
    passes = int(sys.argv[3]) if len(sys.argv) > 3 else 5
    out_dir = Path(sys.argv[4]) if len(sys.argv) > 4 else Path("grid_drift_diagnostic")

    sys.exit(main(plate_type, well, passes, out_dir))
