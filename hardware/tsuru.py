"""Serial control for the Tsuru scanning gantry, replacing the Kamome gantry
(hardware/kamome.py) for multi-mode characterization - PL, UV-Vis, and
camera positions are all reachable off one calibrated plate anchor
(tsuru_sdk.config.PLATE_TYPES) plus a per-mode XY delta. See
tsuru_sdk.config for the deltas/plate geometry and tsuru_sdk.tsuru.Tsuru for
the gantry wrapper itself (connect/home/move_to_well/scan_plate).

Currently calibrated modes: PL and Camera. UV-Vis has no measured delta yet
(tsuru_sdk.config.UVVIS_DELTA is None) - move_to_well(Mode.UV_VIS, ...) will
raise until that's calibrated on the physical rig.

Vendor SDK: https://github.com/tamuracn/Tsuru - a separate installable
package (`tsuru_sdk`), not part of this repo, same as kamome_sdk before it.
Installed editable via `uv pip install -e ../Tsuru` (sibling checkout).
"""

from tsuru_sdk import Mode, Tsuru
from tsuru_sdk.config import PLATE_TYPES

PORT = "COM3"  # Windows - use "/dev/ttyUSB0" on Linux/Mac
PLATE_TYPE = "Thinfilm_20"

if __name__ == "__main__":
    with Tsuru(PORT) as gantry:
        for well in ("A1", "A2", "A3"):
            gantry.move_to_well(Mode.PL, PLATE_TYPE, well)
            print(f"Arrived at {well}")

        gantry.home()
