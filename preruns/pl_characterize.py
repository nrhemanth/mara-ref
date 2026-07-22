"""PL characterization run: collect a background-subtracted photoluminescence
spectrum from each of 16 film samples on a 4x5 thin-film plate, via the
Kamome gantry (hardware/kamome.py) and the Ocean HDX spectrometer
(hardware/ocean_HDX.py).

This isn't an Opentrons protocol - Kamome and the Ocean HDX aren't OT-2
hardware, they're driven directly from this computer over serial/USB, so
there's no protocols/*.py file or robot upload involved here, unlike the
other scripts in this package.

Plate layout: 4 rows x 5 columns ("Thinfilm_20" in kamome_sdk.PLATE_TYPES).
Samples occupy columns 1-4 (A1..D4, 16 wells) - column 5 has no films on it
and is never visited.

Usage:
    python -m preruns.pl_characterize results/ input/0713_batch_1.csv
    KAMOME_PORT=COM5 python -m preruns.pl_characterize results/ input/0713_batch_1.csv

    # measure only a subset of wells, e.g. because the rest of the plate
    # isn't filled yet - pass an inclusive well range in plate order:
    python -m preruns.pl_characterize results/ input/0713_batch_1.csv C1-D4

    # calibrate A1 for this plate: homes, then jogs from (0, 0) - see
    # hardware.kamome.calibrate_a1 for the interactive controls
    python -m preruns.pl_characterize calibrate
    KAMOME_PORT=COM5 python -m preruns.pl_characterize calibrate

The batch name embedded in each output filename (e.g. 0713_batch_1_A1.csv) is
taken from the samples CSV's stem, so spectra stay traceable to the input file
that defined that plate's samples.
"""

from __future__ import annotations

import csv
import os
import sys
from pathlib import Path

from hardware.kamome import Kamome
from hardware.ocean_HDX import OceanHDX

DEFAULT_PORT = "COM3"
PLATE_TYPE = "Thinfilm_20"
SAMPLE_WELLS = [f"{row}{col}" for row in "ABCD" for col in range(1, 5)]  # A1..D4, 16 samples


def write_spectrum_csv(path: Path, wavelengths: list[float], intensities: list[float]) -> None:
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["wavelength_nm", "intensity"])
        writer.writerows(zip(wavelengths, intensities))


def parse_well_range(spec: str) -> list[str]:
    """Parse an inclusive well range like "C1-D4" into plate-order wells.

    Range endpoints must both appear in SAMPLE_WELLS (row-major A1..D4 order);
    the slice is taken in that order, not a rectangular grid selection.
    """
    start, _, end = spec.partition("-")
    if not end:
        raise ValueError(f"invalid well range {spec!r}, expected e.g. 'C1-D4'")
    try:
        start_idx = SAMPLE_WELLS.index(start)
        end_idx = SAMPLE_WELLS.index(end)
    except ValueError:
        raise ValueError(f"invalid well range {spec!r}: wells must be one of {SAMPLE_WELLS}")
    if start_idx > end_idx:
        raise ValueError(f"invalid well range {spec!r}: start comes after end in plate order")
    return SAMPLE_WELLS[start_idx : end_idx + 1]


def main(out_dir: Path, samples_csv: Path, wells: list[str] | None = None) -> int:
    kamome_port = os.environ.get("KAMOME_PORT", DEFAULT_PORT)
    out_dir.mkdir(parents=True, exist_ok=True)
    batch = samples_csv.stem
    wells = wells if wells is not None else SAMPLE_WELLS

    summary_rows = []

    with OceanHDX(integration_time_us=500_000) as spec:
        input("Cap the probe / block excitation, then press Enter to capture background...")
        spec.capture_background()
        wavelengths = spec.get_wavelengths()

        with Kamome(kamome_port) as gantry:
            gantry.check_connection()

            for well in wells:
                gantry.move_to_well(PLATE_TYPE, well)
                intensities = spec.get_spectrum()
                write_spectrum_csv(out_dir / f"{batch}_{well}.csv", wavelengths, intensities)

                peak_intensity = max(intensities)
                peak_wavelength = wavelengths[intensities.index(peak_intensity)]
                summary_rows.append((f"{batch}_{well}", peak_wavelength, peak_intensity))
                print(f"{batch}_{well}: peak={peak_intensity:.1f} at {peak_wavelength:.1f} nm")

            gantry.home()

    with open(out_dir / "summary.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["sample_id", "peak_wavelength_nm", "peak_intensity"])
        writer.writerows(summary_rows)

    print(f"Done. {len(wells)} spectra written to {out_dir}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "calibrate":
        from hardware.kamome import calibrate_a1

        kamome_port = os.environ.get("KAMOME_PORT", DEFAULT_PORT)
        step_mm = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
        calibrate_a1(kamome_port, PLATE_TYPE, step_mm=step_mm)
        sys.exit(0)

    if len(sys.argv) < 3:
        print("Usage: python -m preruns.pl_characterize <out_dir> <samples_csv> [well_range]", file=sys.stderr)
        sys.exit(2)
    out_dir = Path(sys.argv[1])
    samples_csv = Path(sys.argv[2])
    wells = parse_well_range(sys.argv[3]) if len(sys.argv) > 3 else None
    sys.exit(main(out_dir, samples_csv, wells))
