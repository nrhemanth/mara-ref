"""Orchestration entry point: scan a well-plate range with the Kamome gantry,
collecting a background-subtracted PL spectrum from the Ocean HDX at each
well.

Unlike the other scripts in this package, this doesn't touch the OT-2 at
all - it drives the Kamome gantry (hardware/kamome.py) and the Ocean HDX
spectrometer (hardware/ocean_HDX.py) directly, on their own serial/USB
connections. Background is captured once at the start (probe capped /
excitation off) and subtracted from every well's spectrum automatically -
see OceanHDX.capture_background().

Usage:
    python -m preruns.pl_scan Corning_96 A1 D6 results/
    KAMOME_PORT=COM5 python -m preruns.pl_scan Corning_96 A1 D6
"""

from __future__ import annotations

import csv
import os
import sys
from pathlib import Path

from hardware.kamome import Kamome
from hardware.ocean_HDX import OceanHDX
from kamome_sdk import PLATE_TYPES

DEFAULT_PORT = "COM3"


def iter_wells(plate_type: str, start_well: str, end_well: str):
    """Row-major well labels from start_well to end_well, inclusive (e.g.
    A1, A2, ..., A12, B1, ...). Not serpentine-optimized like Kamome's
    autonomous scan() - each well is an explicit move_to_well() call here,
    so visit order doesn't affect anything but total travel distance."""
    if plate_type not in PLATE_TYPES:
        available = ", ".join(PLATE_TYPES.keys())
        raise ValueError(f"Unknown plate type '{plate_type}'. Available: {available}")

    plate = PLATE_TYPES[plate_type]
    start_row, start_col = ord(start_well[0].upper()) - ord("A") + 1, int(start_well[1:])
    end_row, end_col = ord(end_well[0].upper()) - ord("A") + 1, int(end_well[1:])

    if start_row > plate["rows"] or end_row > plate["rows"]:
        raise ValueError(f"Row out of range for this plate (max {plate['rows']} rows).")
    if start_col > plate["cols"] or end_col > plate["cols"]:
        raise ValueError(f"Column out of range for this plate (max {plate['cols']} cols).")

    for row in range(start_row, end_row + 1):
        row_letter = chr(ord("A") + row - 1)
        for col in range(start_col, end_col + 1):
            yield f"{row_letter}{col}"


def write_spectrum_csv(path: Path, wavelengths: list[float], intensities: list[float]) -> None:
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["wavelength_nm", "intensity"])
        writer.writerows(zip(wavelengths, intensities))


def main(plate_type: str, start_well: str, end_well: str, out_dir: Path) -> int:
    kamome_port = os.environ.get("KAMOME_PORT", DEFAULT_PORT)
    out_dir.mkdir(parents=True, exist_ok=True)

    wells = list(iter_wells(plate_type, start_well, end_well))

    with OceanHDX() as spec:
        input("Cap the probe / block excitation, then press Enter to capture background...")
        spec.capture_background()
        wavelengths = spec.get_wavelengths()

        with Kamome(kamome_port) as gantry:
            gantry.check_connection()

            for well in wells:
                gantry.move_to_well(plate_type, well)
                intensities = spec.get_spectrum()
                write_spectrum_csv(out_dir / f"{well}.csv", wavelengths, intensities)
                print(f"{well}: saved ({len(intensities)} points, peak={max(intensities):.1f})")

            gantry.home()

    print(f"Done. {len(wells)} spectra written to {out_dir}")
    return 0


if __name__ == "__main__":
    plate_type = sys.argv[1]
    start_well = sys.argv[2]
    end_well = sys.argv[3]
    out_dir = Path(sys.argv[4]) if len(sys.argv) > 4 else Path("pl_scan_results")

    sys.exit(main(plate_type, start_well, end_well, out_dir))
