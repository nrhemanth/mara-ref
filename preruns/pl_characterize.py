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
    python -m preruns.pl_characterize results/
    KAMOME_PORT=COM5 python -m preruns.pl_characterize results/
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


def main(out_dir: Path) -> int:
    kamome_port = os.environ.get("KAMOME_PORT", DEFAULT_PORT)
    out_dir.mkdir(parents=True, exist_ok=True)

    summary_rows = []

    with OceanHDX() as spec:
        input("Cap the probe / block excitation, then press Enter to capture background...")
        spec.capture_background()
        wavelengths = spec.get_wavelengths()

        with Kamome(kamome_port) as gantry:
            gantry.check_connection()

            for well in SAMPLE_WELLS:
                gantry.move_to_well(PLATE_TYPE, well)
                intensities = spec.get_spectrum()
                write_spectrum_csv(out_dir / f"{well}.csv", wavelengths, intensities)

                peak_intensity = max(intensities)
                peak_wavelength = wavelengths[intensities.index(peak_intensity)]
                summary_rows.append((well, peak_wavelength, peak_intensity))
                print(f"{well}: peak={peak_intensity:.1f} at {peak_wavelength:.1f} nm")

            gantry.home()

    with open(out_dir / "summary.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["sample_id", "peak_wavelength_nm", "peak_intensity"])
        writer.writerows(summary_rows)

    print(f"Done. {len(SAMPLE_WELLS)} spectra written to {out_dir}")
    return 0


if __name__ == "__main__":
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("pl_characterize_results")
    sys.exit(main(out_dir))
