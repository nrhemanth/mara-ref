from typing import Any, Dict

from opentrons.protocol_api import SINGLE
from opentrons.types import Point

requirements = {"robotType": "OT-2", "apiLevel": "2.27"}

# ---------------------------------------------------------------------------
# Standalone position-check protocol.
#
# The hotplate now sits on slot 6 and extends back to slot 9 (OT-2 slots 6
# and 9 are adjacent front/back, so this is one continuous deeper surface
# in Y). There's no Opentrons labware definition for the hotplate itself,
# so a PCR plate is loaded in slot 6 purely to get a stable deck reference
# frame -- set_offset plus the per-spot x/y/z offsets below are what
# actually align the grid to the physical plate.
#
# Tune GRID_* below and re-run until the pipette lines up with your spots.
# ---------------------------------------------------------------------------

GRID_COLS = 4          # spots across (X) per row
GRID_ROWS = 4          # spots deep (Y), within slot 6's own footprint
GRID_PITCH = (115.0 - 22.0) / 3  # mm between adjacent spots -- 4x 22mm films spanning 12cm total edge-to-edge
GRID_X_OFFSET = None   # mm from anchor's A1 in X; None = center on GRID_PITCH
GRID_Y_OFFSET = None  # mm from anchor's A1 in Y; None = center on GRID_PITCH
GRID_Z_OFFSET = -7.0   # mm added to the heater-top Z (83 mm, set below)
HOVER_HEIGHT = 1.0     # mm above each spot to hover at for a visual check
POS_XY_CHECK = False #True

def set_film_plate_grid(
    protocol,
    slot,
    n_cols: int = GRID_COLS,
    n_rows: int = GRID_ROWS,
    pitch: float = GRID_PITCH,
    x_offset: float = GRID_X_OFFSET,
    y_offset: float = GRID_Y_OFFSET,
    z_offset: float = GRID_Z_OFFSET,
):
    """n_cols x n_rows drop-cast grid on a hotplate, anchored off a PCR plate
    loaded in the given slot purely for a stable deck reference frame.
    Defaults center the grid on `pitch`-spaced spots starting from A1.
    The plate sits on top of a heater, hence z=87 mm (heater top) below.
    """
    if x_offset is None:
        x_offset = pitch / 2
    if y_offset is None:
        y_offset = pitch / 2

    plate_film = protocol.load_labware('opentrons_96_wellplate_200ul_pcr_full_skirt', slot)
    plate_film.set_offset(x=3, y=1.5, z=83) # plate off set --> A1 off set

    anchor = plate_film['A1']
    film_wells = {}
    key = 1
    for row in range(n_rows):
        for col in range(n_cols):
            x = x_offset + col * pitch
            y = y_offset - row * pitch  # negative = forward, toward the front of the deck
            film_wells[key] = (anchor, (x, y, z_offset))
            key += 1
    return plate_film, film_wells


# ---------------------------------------------------------------------------
# Z-jog helper: sweep a single spot through a range of Z offsets to find the
# height where the tip just touches the glass, without editing GRID_Z_OFFSET
# and re-uploading for every guess. Use the paper-drag test: lay a thin strip
# of paper (or a spare glass slide) at the spot, and pause at each step to
# check whether the tip grips/drags it yet.
# ---------------------------------------------------------------------------
RUN_Z_JOG = True    # Set True to run the Z-jog sweep instead of the full grid check
Z_JOG_SPOT = 1       # which film_wells key to jog at (pick a spot you can easily see/reach)
Z_JOG_START = -3.0   # mm -- first (highest/safest) z offset to try
Z_JOG_STOP = -12.0   # mm -- last (lowest) z offset to try
Z_JOG_STEP = -0.5     # mm -- step size; must be negative (descending from START toward STOP)


def jog_z_at_spot(
    protocol,
    pip20,
    film_wells: Dict[int, Any],
    spot_key: int = Z_JOG_SPOT,
    z_start: float = Z_JOG_START,
    z_stop: float = Z_JOG_STOP,
    z_step: float = Z_JOG_STEP,
) -> None:
    """Hold position at one film-plate spot and step the pipette down through a
    range of Z offsets, pausing at each so you can check how close the tip is
    to the glass (e.g. via the paper-drag test). Use this to find the exact
    touching point before setting GRID_Z_OFFSET for real -- much faster than
    editing the constant and re-uploading for every guess.
    """
    if z_step >= 0:
        raise ValueError(f"z_step must be negative (descending), got {z_step}")
    if z_start < z_stop:
        raise ValueError(f"z_start ({z_start}) must be above z_stop ({z_stop})")

    anchor, (ox, oy, _) = film_wells[spot_key]
    pip20.pick_up_tip()

    z = z_start
    while z >= z_stop:
        location = anchor.top(z=z).move(Point(ox, oy, 0))
        pip20.move_to(location)
        protocol.pause(
            f"Spot {spot_key}: z_offset={z:.2f} (added to the heater-top Z). "
            f"Check the tip-to-glass gap, then resume to step further down."
        )
        z += z_step

    pip20.drop_tip()


def test_film_plate_positions(
    protocol,
    pip20,
    film_wells: Dict[int, Any],
    hover_height: float = HOVER_HEIGHT,
    pause: bool = True,
) -> None:
    """Pick up a single tip and step through every grid spot, pausing at each
    one so the position can be checked against the physical hotplate before
    running a real drop cast. Tune the GRID_* constants above between runs
    based on what you see, then re-upload and re-run."""
    pip20.pick_up_tip()

    for key in sorted(film_wells.keys()):
        anchor, (ox, oy, oz) = film_wells[key]
        location = anchor.top(z=hover_height + oz).move(Point(ox, oy, 0))
        pip20.move_to(location)
        if pause:
            protocol.pause(
                f"Spot {key}/{len(film_wells)}: hovering at x={ox:.1f}, y={oy:.1f}, "
                f"z={hover_height + oz:.1f} above A1. Check alignment, take notes, then resume."
            )
        else: 
            protocol.delay(seconds=3)

    pip20.drop_tip()
    

def run(protocol):
    # Working layout
    '''
    [ 10 empty   ]  [ 11 empty   ]  [ trash  ]
    [  7 empty ]  [  8 empty  ]  [  9 heater  ]
    [  4 empty    ]  [  5 empty   ]  [  6 film_plate on heater ]
    [  1 empty ]  [  2 tiprack_20  ]  [  3 tiprack_300 ] ]

    Hotplate is anchored at slot 6 and extends back to slot 9 -- the grid
    below runs deeper in Y to reach it.
    '''
    tiprack_20 = protocol.load_labware("opentrons_96_tiprack_20ul", "2")
    pip20 = protocol.load_instrument('p20_multi_gen2', mount='right', tip_racks=[tiprack_20])
    pip20.configure_nozzle_layout(style=SINGLE, start="H1", tip_racks=[tiprack_20])

    plate_film, film_wells = set_film_plate_grid(
        protocol, "6",
        n_cols=GRID_COLS, n_rows=GRID_ROWS, pitch=GRID_PITCH,
        x_offset=GRID_X_OFFSET, y_offset=GRID_Y_OFFSET, z_offset=GRID_Z_OFFSET,
    )

    protocol.home()

    if RUN_Z_JOG:
        protocol.comment(f"=== Z-jog at spot {Z_JOG_SPOT}: {Z_JOG_START} to {Z_JOG_STOP} mm, step {Z_JOG_STEP} ===")
        jog_z_at_spot(protocol, pip20, film_wells)
        protocol.comment("=== Z-jog complete ===")
        return
    if POS_XY_CHECK:
        protocol.comment(f"=== Film plate position check: {GRID_COLS}x{GRID_ROWS} grid, anchored at slot 6 ===")
        test_film_plate_positions(protocol, pip20, film_wells, hover_height=HOVER_HEIGHT, pause=False)
    protocol.comment("=== Position check complete ===")
