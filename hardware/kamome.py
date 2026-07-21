"""Serial control for the Kamome scanning gantry that holds the Ocean HDX
probe, via the vendor `kamome_sdk` package (a separate installable SDK, not
part of this repo - github.com/.../Kamome-sdk).

`Kamome.scan()`/`scan_full()` hand the whole well range to the Arduino,
which sweeps it autonomously and only reports back once the entire run is
done - that leaves no point to synchronize a spectrometer read with the
probe actually sitting at a given well. For that, use the addressable
interface instead: `move_to_well()` moves to exactly one well and blocks
until the gantry has arrived and stopped there.

Addressable moves need a session held open across calls (`with Kamome(...)
as gantry:`) - reopening the connection per move, the way scan()/calibrate()
do, would reset the Arduino and lose track of the gantry's physical
position.
"""

from kamome_sdk import Kamome

PORT = "COM3"  # Windows - use "/dev/ttyUSB0" on Linux/Mac
PLATE_TYPE = "Corning_96"

if __name__ == "__main__":
    with Kamome(PORT) as gantry:
        gantry.check_connection()

        for well in ("A1", "A2", "A3"):
            gantry.move_to_well(PLATE_TYPE, well)
            print(f"Arrived at {well}")

        gantry.home()
