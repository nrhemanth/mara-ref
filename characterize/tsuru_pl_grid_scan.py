"""Orchestration entry point: scan a well-plate range with the Tsuru gantry,
collecting 9 background-subtracted PL spectra per well - a 3x3 grid of points
10mm apart, centered on the well's calibrated center - instead of just one
spectrum at the center (see characterize/tsuru_pl_scan.py for the single-point
version). Useful when the film doesn't reliably end up centered in the well.

Grid points are labeled 1-9 like a numpad, 5 = center:
    1 2 3
    4 5 6
    7 8 9
Collection snakes per well: 1>2>3>6>5>4>7>8>9 (row-major serpentine).

No firmware or tsuru_sdk changes needed. Tsuru.move_well only knows how to
target a labeled well on a *plate*, computed from a PlateType's offset/spacing
- there's no lower-level "nudge by X/Y mm" primitive exposed. So each real
well's 3x3 grid is itself modeled as a temporary, throwaway 3-row/3-col
PlateType (10mm spacing) whose own A1 anchor is algebraically placed so that
its center well (its "B2") lands exactly on the real well's calibrated
center - registered into tsuru_sdk.config.PLATE_TYPES under a scratch key,
then scanned with the ordinary Tsuru.scan_plate(). The firmware-side
probeHolderX/Y correction (see tsuru_sdk/config.py's module docstring) is
folded into every move_well the same way regardless of which PlateType made
the call, so it cancels out of this construction automatically.

Sign caveat: this assumes +Y (as sent to move_well) is physically "toward
row A" / "up" on the bench, matching the assumption behind the PLATE_TYPES
offset_y calibration itself. That's unverified hardware-direction knowledge,
not something derivable from code - jog to well label 2 (should read as
"up"/toward row A from center) vs label 8 before trusting a real run, and
flip GRID_ROW_DIST's sign below if it's backwards.

samples.csv must have one row per well, with columns: film_num, film_well,
sample_id. Output files are named <well>_<sample_id>_<point>.csv / .txt (e.g.
A1_FOKYMT_5.csv for A1's center point), so all 9 points per well plus every
well/sample stay distinct.

Usage:
    python -m characterize.tsuru_pl_grid_scan Thinfilm_20 A1 D4 samples.csv results/
    TSURU_PORT=COM6 python -m characterize.tsuru_pl_grid_scan Thinfilm_20 A1 D4 samples.csv
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from characterize.tsuru_pl_scan import read_sample_ids, write_spectrum_csv, write_spectrum_txt
from hardware.ocean_HDX import OceanHDX
from hardware.tsuru import PORT as DEFAULT_PORT
from tsuru_sdk import Mode, Tsuru
from tsuru_sdk import config as tsuru_config
from tsuru_sdk.config import PLATE_TYPES, PlateType
from tsuru_sdk.tsuru import _well_row_col

GRID_STEP_MM = 15.0  # spacing between adjacent grid points, in both X and Y
GRID_COL_DIST = GRID_STEP_MM  # +X = further right, matching every real PlateType's convention
GRID_ROW_DIST = GRID_STEP_MM  # see "Sign caveat" in the module docstring
GRID_KEY = "_pl_grid_scan_scratch"  # scratch PLATE_TYPES entry, overwritten per well

# Tsuru.scan_plate fires each move_well the instant the previous one reports
# "At well", with no settle time - at the grid's tight 10-15mm spacing the
# back-to-back direction reversals (e.g. row A's A1->A2->A3 immediately
# followed by row B running the other way) were observed to make the gantry
# drift. Dwell after every move (grid point and real well alike) before the
# next move_well goes out. Override via env var to tune without editing code.
SETTLE_SECONDS = float(os.environ.get("SETTLE_SECONDS", "0.4"))

# virtual-grid well label ("A1".."C3") -> numpad-style point label (1-9)
GRID_POINT_LABEL = {f"{row}{col}": (r - 1) * 3 + col for r, row in enumerate("ABC", 1) for col in (1, 2, 3)}


def register_grid_plate_type(plate_type: str, well: str) -> None:
    """Register a scratch 3x3, 10mm-spaced PlateType under GRID_KEY whose
    center well (virtual "B2") lands on `well`'s calibrated center on
    `plate_type` - see module docstring for the derivation."""
    plate = PLATE_TYPES[plate_type]
    delta = tsuru_config.PL_DELTA
    well_row, well_col = _well_row_col(well)

    center_x = (plate.offset_x + delta.dx) + (well_col - 1) * plate.col_dist
    center_y = (plate.offset_y + delta.dy) + (plate.rows - well_row) * plate.row_dist

    PLATE_TYPES[GRID_KEY] = PlateType(
        offset_x=center_x - delta.dx - GRID_COL_DIST,
        offset_y=center_y - delta.dy - GRID_ROW_DIST,
        col_dist=GRID_COL_DIST,
        row_dist=GRID_ROW_DIST,
        rows=3,
        cols=3,
    )


def main(plate_type: str, start_well: str, end_well: str, samples_csv: Path, out_dir: Path) -> int:
    if plate_type not in PLATE_TYPES:
        available = ", ".join(PLATE_TYPES.keys())
        raise ValueError(f"Unknown plate type '{plate_type}'. Available: {available}")

    sample_ids = read_sample_ids(samples_csv)
    tsuru_port = os.environ.get("TSURU_PORT", DEFAULT_PORT)
    out_dir.mkdir(parents=True, exist_ok=True)
    scanned: list[str] = []

    with OceanHDX() as spec:
        input("Cap the probe / block excitation, then press Enter to capture background...")
        spec.capture_background()
        wavelengths = spec.get_wavelengths()
        metadata = spec.get_metadata()

        with Tsuru(tsuru_port) as gantry:

            def on_well(well: str) -> None:
                if well not in sample_ids:
                    raise ValueError(f"No sample_id for well '{well}' in {samples_csv}")
                sample_id = sample_ids[well]
                register_grid_plate_type(plate_type, well)

                def on_grid_point(grid_well: str) -> None:
                    point = GRID_POINT_LABEL[grid_well]
                    stem = f"{well}_{sample_id}_{point}"
                    intensities = spec.get_spectrum()
                    write_spectrum_csv(out_dir / f"{stem}.csv", wavelengths, intensities)
                    write_spectrum_txt(out_dir / f"{stem}.txt", metadata, wavelengths, intensities)
                    print(f"{well} point {point}: saved as {stem} (peak={max(intensities):.1f})")
                    time.sleep(SETTLE_SECONDS)

                gantry.scan_plate(Mode.PL, GRID_KEY, "A1", "C3", on_well=on_grid_point)
                scanned.append(well)
                time.sleep(SETTLE_SECONDS)

            gantry.scan_plate(Mode.PL, plate_type, start_well, end_well, on_well=on_well)
            gantry.home()

    print(f"Done. {len(scanned)} wells x 9 points written to {out_dir}")
    return 0


if __name__ == "__main__":
    plate_type = sys.argv[1]
    start_well = sys.argv[2]
    end_well = sys.argv[3]
    samples_csv = Path(sys.argv[4])
    out_dir = Path(sys.argv[5]) if len(sys.argv) > 5 else Path("pl_grid_scan_results")

    sys.exit(main(plate_type, start_well, end_well, samples_csv, out_dir))
