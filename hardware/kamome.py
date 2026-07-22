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

from kamome_sdk import Kamome, KamomeConnection, PLATE_TYPES, PROBE_HOLDERS

PORT = "COM3"  # Windows - use "/dev/ttyUSB0" on Linux/Mac
PLATE_TYPE = "Corning_96"


def _parse_well(well: str) -> tuple[int, int]:
    """'D4' -> (row=4, col=4)."""
    well = well.strip().upper()
    return ord(well[0]) - ord("A") + 1, int(well[1:])


def _jog(conn: KamomeConnection, x: float, y: float, step_mm: float) -> tuple[float, float] | None:
    """Interactive jog loop shared by calibrate_a1/calibrate_plate. Sends raw
    `park,<label>,<x>,<y>` moves (the firmware command Kamome.park() only
    exposes for the two hardcoded PARK_POSITIONS) so this can jog to any
    absolute XY with the motors powered - there's no encoder to sense a
    position the motors didn't drive to themselves.

    Returns the final (x, y) once you type 'done', or None if you type
    'cancel'.
    """
    conn.send(f"park,calib,{x},{y}")
    conn.read_until(sentinel="At park: calib")
    print(
        f"At estimate (x={x:.3f}, y={y:.3f}). Jog until the probe is exactly over "
        f"the physical well.\nCommands: x+ x- y+ y- (step={step_mm}mm), 'step <mm>', 'done', 'cancel'"
    )
    while True:
        cmd = input(f"[step={step_mm}mm] > ").strip().lower()
        if cmd in ("done", "d"):
            return x, y
        if cmd in ("cancel", "c"):
            return None
        if cmd.startswith("step"):
            try:
                step_mm = float(cmd.split()[1])
            except (IndexError, ValueError):
                print("Usage: step <mm>, e.g. 'step 0.5'")
            continue
        delta = {
            "x+": (step_mm, 0), "x-": (-step_mm, 0),
            "y+": (0, step_mm), "y-": (0, -step_mm),
        }.get(cmd)
        if delta is None:
            print("Unrecognized command.")
            continue
        x += delta[0]
        y += delta[1]
        conn.send(f"park,calib,{x},{y}")
        conn.read_until(sentinel="At park: calib")
        print(f"x={x:.3f}, y={y:.3f}")


def _get_plate_and_holder(plate_type: str, probe_holder: str) -> tuple[dict, dict]:
    if plate_type not in PLATE_TYPES:
        available = ", ".join(PLATE_TYPES.keys())
        raise ValueError(f"Unknown plate type '{plate_type}'. Available: {available}")
    if probe_holder not in PROBE_HOLDERS:
        available = ", ".join(PROBE_HOLDERS.keys())
        raise ValueError(f"Unknown probe holder '{probe_holder}'. Available: {available}")
    return PLATE_TYPES[plate_type], PROBE_HOLDERS[probe_holder]


def calibrate_a1(port: str, plate_type: str, probe_holder: str = "Angled", step_mm: float = 1.0) -> None:
    """Interactively jog the probe onto the real A1 well and derive the
    corrected offsetX/offsetY for `plate_type`. This only fixes the A1
    anchor point - if wells further into the plate are off too, that's
    colDist/rowDist (well spacing), which needs calibrate_plate() instead.

    Homes the gantry and starts jogging from there - (0, 0) - rather than
    jumping straight to the *current* (assumed-wrong) offsets, since that
    guess could be off by enough to drive the gantry past its physical
    travel and into the bounds. You jog the whole way from home to A1
    yourself. Reports the corrected offsetX/offsetY to paste into
    kamome_sdk/config.py's PLATE_TYPES entry - it does not modify that file.

    Example:
        python -m hardware.kamome calibrate COM3 Thinfilm_20
    """
    plate, holder = _get_plate_and_holder(plate_type, probe_holder)

    with KamomeConnection(port) as conn:
        conn.send("home")
        conn.read_until(sentinel="At home")
        print("Homed. Jog from (0, 0) to the physical A1 well.")
        result = _jog(conn, 0.0, 0.0, step_mm)
        conn.send("home")
        conn.read_until(sentinel="At home")

    if result is None:
        print("Cancelled - offsets unchanged.")
        return
    x, y = result

    new_offset_x = x - holder["x"]
    new_offset_y = y - holder["y"] - (plate["rows"] - 1) * plate["rowDist"]

    print(f"\nCalibrated A1 for '{plate_type}' (probe holder: {probe_holder}):")
    print(f"  offsetX: {plate['offsetX']:.3f} -> {new_offset_x:.3f}")
    print(f"  offsetY: {plate['offsetY']:.3f} -> {new_offset_y:.3f}")
    print(
        f"\nUpdate kamome_sdk/config.py PLATE_TYPES['{plate_type}']:\n"
        f'    "offsetX": {new_offset_x:.3f}, "offsetY": {new_offset_y:.3f},'
    )


def calibrate_plate(
    port: str,
    plate_type: str,
    corner_well: str,
    probe_holder: str = "Angled",
    step_mm: float = 1.0,
) -> None:
    """Interactively jog to A1 and a second, far well to derive corrected
    offsetX/offsetY *and* colDist/rowDist for `plate_type` in one pass.

    `corner_well` should be the farthest real well you can see, in a
    different row AND column from A1 - e.g. "D4" on a plate whose last
    column has no film in it (so there's nothing to visually align to at the
    nominal last column/row). X depends only on column and Y only on column
    in the firmware's move formula, so any well differing in both axes from
    A1 is enough to pin down colDist and rowDist independently - it doesn't
    need to be the plate's nominal last row/column.

    Jogs the same way as calibrate_a1 - starting from home, (0, 0), rather
    than jumping to a formula-based guess that could drive the gantry past
    its physical travel and into the bounds. Both A1 and the corner well are
    jogged to from a fresh home, not chained off each other, so a bad guess
    in one step can't carry into the next. Motors stay powered throughout -
    there's no encoder to read a manually-pushed position back.
    Reports corrected offsetX/offsetY/colDist/rowDist to paste into
    kamome_sdk/config.py - it does not modify that file.

    Example:
        python -m hardware.kamome calibrate-plate COM3 Thinfilm_20 D4
    """
    plate, holder = _get_plate_and_holder(plate_type, probe_holder)
    row2, col2 = _parse_well(corner_well)
    if row2 == 1 or col2 == 1:
        raise ValueError(
            f"corner_well '{corner_well}' must differ from A1 in both row and column "
            "to pin down colDist and rowDist independently."
        )

    with KamomeConnection(port) as conn:
        conn.send("home")
        conn.read_until(sentinel="At home")

        print("Step 1/2: jog from (0, 0) to A1.")
        result1 = _jog(conn, 0.0, 0.0, step_mm)
        if result1 is None:
            conn.send("home")
            conn.read_until(sentinel="At home")
            print("Cancelled - nothing changed.")
            return
        x1, y1 = result1

        conn.send("home")
        conn.read_until(sentinel="At home")
        print(f"Step 2/2: jog from (0, 0) to {corner_well.upper()}.")
        result2 = _jog(conn, 0.0, 0.0, step_mm)
        conn.send("home")
        conn.read_until(sentinel="At home")

    if result2 is None:
        print("Cancelled - nothing changed.")
        return
    x2, y2 = result2

    new_col_dist = (x2 - x1) / (col2 - 1)
    new_row_dist = (y1 - y2) / (row2 - 1)
    new_offset_x = x1 - holder["x"]
    new_offset_y = y1 - holder["y"] - (plate["rows"] - 1) * new_row_dist

    print(f"\nCalibrated '{plate_type}' from A1 + {corner_well.upper()} (probe holder: {probe_holder}):")
    print(f"  offsetX: {plate['offsetX']:.3f} -> {new_offset_x:.3f}")
    print(f"  offsetY: {plate['offsetY']:.3f} -> {new_offset_y:.3f}")
    print(f"  colDist: {plate['colDist']:.3f} -> {new_col_dist:.3f}")
    print(f"  rowDist: {plate['rowDist']:.3f} -> {new_row_dist:.3f}")
    print(
        f"\nUpdate kamome_sdk/config.py PLATE_TYPES['{plate_type}']:\n"
        f'    "offsetX": {new_offset_x:.3f}, "offsetY": {new_offset_y:.3f},\n'
        f'    "colDist": {new_col_dist:.3f}, "rowDist": {new_row_dist:.3f},'
    )


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "calibrate":
        if len(sys.argv) < 4:
            print("Usage: python -m hardware.kamome calibrate <port> <plate_type> [step_mm]", file=sys.stderr)
            sys.exit(2)
        calibrate_a1(sys.argv[2], sys.argv[3], step_mm=float(sys.argv[4]) if len(sys.argv) > 4 else 1.0)
    elif len(sys.argv) > 1 and sys.argv[1] == "calibrate-plate":
        if len(sys.argv) < 5:
            print(
                "Usage: python -m hardware.kamome calibrate-plate <port> <plate_type> <corner_well> [step_mm]",
                file=sys.stderr,
            )
            sys.exit(2)
        calibrate_plate(
            sys.argv[2], sys.argv[3], sys.argv[4],
            step_mm=float(sys.argv[5]) if len(sys.argv) > 5 else 1.0,
        )
    else:
        with Kamome(PORT) as gantry:
            gantry.check_connection()

            for well in ("A1", "A2", "A3"):
                gantry.move_to_well(PLATE_TYPE, well)
                print(f"Arrived at {well}")

            gantry.home()
