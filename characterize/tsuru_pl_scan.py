"""Orchestration entry point: scan a well-plate range with the Tsuru gantry,
collecting a background-subtracted PL spectrum from the Ocean HDX at each
well.

Tsuru replacement for preruns/pl_scan.py's Kamome-based version. Doesn't
touch the OT-2 at all - drives the Tsuru gantry (hardware/tsuru.py) and the
Ocean HDX spectrometer (hardware/ocean_HDX.py) directly, on their own
serial/USB connections. Background is captured once at the start (probe
capped / excitation off) and subtracted from every well's spectrum
automatically - see OceanHDX.capture_background().

Unlike the Kamome version, well iteration doesn't need to be hand-rolled
here - Tsuru.scan_plate() already sweeps a plate's well range itself and
calls back per well once the gantry has arrived and settled.

samples.csv must have one row per well, with columns: film_num, film_well, sample_id.
Output files are named <well>_<sample_id>.csv / .txt (e.g. A1_FOKYMT.csv), so
they don't collide with the same well from a different plate/run.

Usage:
    python -m preruns.tsuru_pl_scan Thinfilm_20 A1 D5 samples.csv results/
    TSURU_PORT=COM5 python -m preruns.tsuru_pl_scan Thinfilm_20 A1 D5 samples.csv
"""

from __future__ import annotations

import csv
import os
import sys
import time
from pathlib import Path

from hardware.ocean_HDX import OceanHDX, OceanHDXMetadata, format_oceanview_txt
from hardware.tsuru import PORT as DEFAULT_PORT
from tsuru_sdk import Mode, Tsuru
from tsuru_sdk.config import PLATE_TYPES

# Tsuru.scan_plate fires each move_well the instant the previous one reports
# "At well", with no settle time - the serpentine sweep reverses X direction
# every other row, and back-to-back reversals were observed to make the
# gantry drift (see characterize/tsuru_pl_grid_scan.py, where this was first
# hit at tighter spacing). Dwell after each well before the next move_well
# goes out. Override via env var to tune without editing code.
SETTLE_SECONDS = float(os.environ.get("SETTLE_SECONDS", "0.4"))


def read_sample_ids(path: Path) -> dict[str, str]:
    with open(path, newline="") as f:
        return {row["film_well"]: row["sample_id"] for row in csv.DictReader(f)}


def write_spectrum_csv(path: Path, wavelengths: list[float], intensities: list[float]) -> None:
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["wavelength_nm", "intensity"])
        writer.writerows(zip(wavelengths, intensities))


def write_spectrum_txt(
    path: Path,
    metadata: OceanHDXMetadata,
    wavelengths: list[float],
    intensities: list[float],
) -> None:
    path.write_text(format_oceanview_txt(path.name, metadata, wavelengths, intensities))


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

        def on_well(well: str) -> None:
            if well not in sample_ids:
                raise ValueError(f"No sample_id for well '{well}' in {samples_csv}")
            stem = f"{well}_{sample_ids[well]}"
            intensities = spec.get_spectrum()
            write_spectrum_csv(out_dir / f"{stem}.csv", wavelengths, intensities)
            write_spectrum_txt(out_dir / f"{stem}.txt", metadata, wavelengths, intensities)
            print(f"{well}: saved as {stem} ({len(intensities)} points, peak={max(intensities):.1f})")
            scanned.append(well)
            time.sleep(SETTLE_SECONDS)

        with Tsuru(tsuru_port) as gantry:
            gantry.scan_plate(Mode.PL, plate_type, start_well, end_well, on_well=on_well)
            gantry.home()

    print(f"Done. {len(scanned)} spectra written to {out_dir}")
    return 0


if __name__ == "__main__":
    plate_type = sys.argv[1]
    start_well = sys.argv[2]
    end_well = sys.argv[3]
    samples_csv = Path(sys.argv[4])
    out_dir = Path(sys.argv[5]) if len(sys.argv) > 5 else Path("pl_scan_results")

    sys.exit(main(plate_type, start_well, end_well, samples_csv, out_dir))
