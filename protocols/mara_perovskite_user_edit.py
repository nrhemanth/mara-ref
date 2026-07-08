import json

import csv
from pathlib import Path
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass
import os
from io import StringIO
    
from opentrons.protocol_api import ProtocolContext, InstrumentContext
from typing import Dict, Any, List, Union
from opentrons import protocol_api
from opentrons.protocol_api import SINGLE, PARTIAL_COLUMN, ALL
from opentrons.types import Point


# ---------------------------------------------------------------------------
# Experiment parameters
# Anything you might want to change between runs lives here at the top,
# not buried in the run() function.
# ---------------------------------------------------------------------------

# CSV served from the shared folder computer on the lab network.
# Start the server with: cd Mara_shared && python -m http.server 8000
CONDITIONS_URL = "http://192.168.0.140:8000/conditions.csv"

# Which columns in the CSV map to the three source solutions (in order):
# source well A1 → BAAc, B1 → MAI, C1 → PbI2
SOLUTION_COLUMNS = ["BAAc_vol", "MAI_vol", "PbI2_vol"]

# Tip to start from for the mixing step.
# Change this if the run is resuming partway through a tip rack.
MIX_TIP_START = "A1"

# Drop-casting volumes (µL)
ASPIRATE_VOL = 5    # how much to pull up from the 96-well plate
DROP_VOL     = 5  # how much to deposit on the substrate

# Number of mix strokes applied to each column during Step 2 mixing.
MIX_CYCLES = 10

# Film-plate drop-cast grid, tuned via dropcast_position.py's position-check script.
GRID_COLS = 4          # spots across (X) per row
GRID_ROWS = 4          # spots deep (Y), within the film plate's own footprint
GRID_PITCH = (115.0 - 22.0) / 3  # mm between adjacent spots -- 4x 22mm films spanning 12cm total edge-to-edge
GRID_X_OFFSET = None   # mm from anchor's A1 in X; None = center on GRID_PITCH
GRID_Y_OFFSET = None   # mm from anchor's A1 in Y; None = center on GRID_PITCH
GRID_Z_OFFSET = -11.5   # mm added to the heater-top Z (80 mm, set in set_film_plate_16) Set at -13.0 when glass + holder
HOVER_HEIGHT = 1.0     # mm above each spot to hover at for a visual check

 # Set True to jog the p20 (single tip) through all 16 film-plate spots, pausing at each one, instead of running the full protocol.
TEST_FILM_PLATE_POSITIONS = False

# Pre-set which steps to run. Edit these before uploading to the robot: on a
# real run through the Opentrons App there's no terminal for input() to read
# from, so these booleans are the only way to skip a step there.
RUN_TRANSFER_PBI2 = False #True
RUN_TRANSFER_BAAC = False #True
RUN_TRANSFER_MAI = False #True
RUN_MIXING = False #True 
RUN_DROP_CASTING = True

# Set True only when running locally via opentrons_execute/opentrons_simulate
# with a terminal attached. Adds a y/n prompt on top of the presets above so
# you can override a step on the fly; leaving it False (the safe default for
# an actual robot run) skips the prompt entirely and just uses the presets.
INTERACTIVE_CONFIRM = False

requirements = {"robotType": "OT-2", "apiLevel": "2.27"}

FILL_MODE = "column"

SAMPLE_DATA = json.loads("""
[
    {"sample_id": 1, "vol_PbI2": 100, "vol_BAAc": 50, "vol_MAI": 50, "time": 30, "temperature": 25},
    {"sample_id": 2, "vol_PbI2": 100, "vol_BAAc": 50, "vol_MAI": 50, "time": 30, "temperature": 25},
    {"sample_id": 3, "vol_PbI2": 80, "vol_BAAc": 70, "vol_MAI": 70, "time": 35, "temperature": 25},
    {"sample_id": 4, "vol_PbI2": 80, "vol_BAAc": 70, "vol_MAI": 70, "time": 30, "temperature": 25},
    {"sample_id": 5, "vol_PbI2": 60, "vol_BAAc": 90, "vol_MAI": 90, "time": 30, "temperature": 25},
    {"sample_id": 6, "vol_PbI2": 60, "vol_BAAc": 90, "vol_MAI": 90, "time": 35, "temperature": 25},
    {"sample_id": 7, "vol_PbI2": 40, "vol_BAAc": 110,"vol_MAI": 110,  "time": 30, "temperature": 25},
    {"sample_id": 8, "vol_PbI2": 40, "vol_BAAc": 110,"vol_MAI": 110,  "time": 35, "temperature": 25},
    {"sample_id": 9, "vol_PbI2": 100, "vol_BAAc": 50, "vol_MAI": 50, "time": 30, "temperature": 25},
    {"sample_id": 10, "vol_PbI2": 100, "vol_BAAc": 50, "vol_MAI": 50, "time": 30, "temperature": 25},
    {"sample_id": 11, "vol_PbI2": 80, "vol_BAAc": 70, "vol_MAI": 70, "time": 35, "temperature": 25},
    {"sample_id": 12, "vol_PbI2": 80, "vol_BAAc": 70, "vol_MAI": 70, "time": 30, "temperature": 25},
    {"sample_id": 13, "vol_PbI2": 60, "vol_BAAc": 90, "vol_MAI": 90, "time": 30, "temperature": 25},
    {"sample_id": 14, "vol_PbI2": 60, "vol_BAAc": 90, "vol_MAI": 90, "time": 35, "temperature": 25},
    {"sample_id": 15, "vol_PbI2": 40, "vol_BAAc": 110,"vol_MAI": 110,  "time": 30, "temperature": 25},
    {"sample_id": 16, "vol_PbI2": 40, "vol_BAAc": 110,"vol_MAI": 110,  "time": 35, "temperature": 25}
]
""")

PRECURSORS = json.loads("""{
    "PbI2": {"name": "PbI2", "well_index": 0, "volume": 9500, "concentration": 1.0, "solvent": "DMF:DMSO"},
    "BAAc": {"name": "BAAc", "well_index": 1, "volume": 9500, "concentration": 0.5, "solvent": "DMF:DMSO"},
    "MAI":  {"name": "MAI",  "well_index": 2, "volume": 9500, "concentration": 1.0, "solvent": "DMF:DMSO"}
}
""")

@dataclass
class SampleParameters:
    """Container for a single sample's parameters."""
    sample_id: int
    vol_PbI2: float  # Volume of PbI2 precursor in µL
    vol_BAAc: float  # Volume of BAAc precursor in µL
    vol_MAI: float   # Volume of MAI precursor in µL
    time: float   # Mixing time in seconds
    temperature: float  # Temperature in °C

@dataclass
class Precursor:
    """Container for a single precursor's parameters."""
    name: str
    well_index: int  # Index of the well in the reservoir (0-based)
    volume: float  # Volume in µL
    concentration: float  # Concentration in Molarity (M)
    solvent: str  # Solvent used for the precursor

def get_precursor(name: str) -> Precursor:
    """Look up a precursor by name."""
    if name not in PRECURSORS:
        raise ValueError(f"Unknown precursor: {name}. Available: {list(PRECURSORS)}")
    return Precursor(**PRECURSORS[name])

#--- Functions for sample parameter validation and conversion ---#
def validate_sample_parameters(samples: List[SampleParameters], fill_mode: str = "row") -> Tuple[bool, str]:
    """Validate sample parameters."""
    if not samples:
        return False, "No samples provided"

    for sample in samples:
        vol_pbi2 = sample.vol_PbI2
        vol_baac = sample.vol_BAAc
        vol_mai = sample.vol_MAI
        time = sample.time
        temp = sample.temperature
        sid = sample.sample_id

        if vol_pbi2 < 0 or vol_pbi2 > 200:
            return False, f"Sample {sid}: vol_PbI2 must be 0-200 µL, got {vol_pbi2}"
        if vol_baac < 0 or vol_baac > 200:
            return False, f"Sample {sid}: vol_BAAc must be 0-200 µL, got {vol_baac}"
        if vol_mai < 0 or vol_mai > 200:
            return False, f"Sample {sid}: vol_MAI must be 0-200 µL, got {vol_mai}"
        if time < 0 or time > 300:
            return False, f"Sample {sid}: time must be 0-300s, got {time}"
        if temp < 0 or temp > 100:
            return False, f"Sample {sid}: temperature must be 0-100°C, got {temp}"

    return True, "All samples valid"

def samples_to_volume_lists(samples: List[SampleParameters], fill_mode: str = "row", index: int = 0) -> Tuple[List[float], List[float], List[float]]:
    """Convert one column/row's worth of sample parameters to volume lists."""
    n = 8 if fill_mode == "column" else 12
    chunk = samples[index * n:(index + 1) * n]

    vol_pbi2_list = [s.vol_PbI2 for s in chunk]
    vol_baac_list = [s.vol_BAAc for s in chunk]
    vol_mai_list = [s.vol_MAI for s in chunk]

    for lst in (vol_pbi2_list, vol_baac_list, vol_mai_list):
        while len(lst) < n:
            lst.append(0)

    return vol_pbi2_list[:n], vol_baac_list[:n], vol_mai_list[:n]


def should_run(step_name: str, preset: bool = True) -> bool:
    """Decide whether to run a step.

    `preset` is what actually controls behavior on the robot/App (set via the
    RUN_* constants above) -- there's no terminal there for input() to read.

    If INTERACTIVE_CONFIRM is True, this additionally prompts in the terminal
    for a y/n override (only meaningful when running locally with a terminal
    attached, e.g. via opentrons_simulate); pressing Enter with no answer
    keeps the preset.
    """
    if not INTERACTIVE_CONFIRM:
        return preset
    default_label = "Y/n" if preset else "y/N"
    answer = input(f"Run {step_name}? [{default_label}]: ").strip().lower()
    if not answer:
        return preset
    return answer in ("y", "yes")


#--- Functions for sample parameter validation and conversion ---#
class Quasi2DProtocol:
    def __init__(self, pip300, pip20, fill_mode: str = "row"):
        self.pip300 = pip300
        self.pip20 = pip20
        self.fill_mode = fill_mode
        self.n_wells = 8 if fill_mode == "column" else 12

    def _get_wells(self, plate, index: int = 0) -> list:
        """Return the target wells for the current fill mode."""
        if self.fill_mode == "column":
            return plate.columns()[index]
        return plate.rows()[index]
    
    def _get_tips_config(self, n, tiprack):
        """Return tip pickup configuration based on number of tips.
        start nozzle: H1
        Possible end nozzles are: G1, F1, E1, D1, C1, B1 | 2, 3, 4, 5, 6, 7

        """
        if n == 1:
            return {"style": SINGLE, "start": "H1", "tip_racks": [tiprack]}
        elif n == 2:
             return {"style": PARTIAL_COLUMN, "start": "H1", "end": "G1", "tip_racks": [tiprack]}
        elif n == 3:
             return {"style": PARTIAL_COLUMN, "start": "H1", "end": "F1", "tip_racks": [tiprack]}   
        elif n == 4:
            return {"style": PARTIAL_COLUMN, "start": "H1", "end": "E1", "tip_racks": [tiprack]}
        elif n == 5:
            return {"style": PARTIAL_COLUMN, "start": "H1", "end": "D1", "tip_racks": [tiprack]}
        elif n == 6:
            return {"style": PARTIAL_COLUMN, "start": "H1", "end": "C1", "tip_racks": [tiprack]}
        elif n == 7:
            return {"style": PARTIAL_COLUMN, "start": "H1", "end": "B1", "tip_racks": [tiprack]}
        else:
            raise ValueError(f"Unsupported batch size for tip configuration: {n}")
        
    def transfer_precursor_batch(self,
        dest_wells: list,
        volumes: List[float],
        source_reservoir,
        tiprack,
        source_well_index: int = 0,
        n: int = 2,
    ) -> None:
        """Transfer to the last well of each n-well group across dest_wells,
        picking up tips once and reusing them for the whole batch -- pass the
        full flat list of wells (e.g. spanning multiple plate columns) to fill
        them all in one pass instead of re-picking tips per column."""
        if len(volumes) != len(dest_wells):
            raise ValueError(f"volumes must match dest_wells length ({len(dest_wells)}), got {len(volumes)}")

        self.pip300.configure_nozzle_layout(**self._get_tips_config(n, tiprack))

        source = source_reservoir.wells()[source_well_index]

        self.pip300.pick_up_tip()
        for i in range(0, len(volumes), n):
            vol = volumes[i]
            if vol > 0:
                self.pip300.aspirate(vol, source)
                self.pip300.dispense(vol, dest_wells[i + n - 1])
        self.pip300.drop_tip()

    def mix_wells_column(
        self,
        dest_plate,
        cycles: int,
        tiprack,
        mix_volume: float = 100,
        dest_index: int = 0,
    ) -> None:
        """Pick up a full column of tips and mix all 8 wells simultaneously,
        `cycles` times."""
        self.pip300.configure_nozzle_layout(style=ALL, tip_racks=[tiprack])

        col_wells = self._get_wells(dest_plate, dest_index)

        self.pip300.pick_up_tip()
        self.pip300.mix(cycles, mix_volume, col_wells[0])
        self.pip300.drop_tip()

    def drop_cast_single(
        self,
        protocol,
        source_wells: list,
        film_wells: Dict[int, Any],
        tiprack,
        volume: float = 5,
        hover_seconds: float = 3,
    ) -> None:
        """Drop cast one film-plate spot at a time: one source well per spot,
        one tip picked up and dropped per drop. source_wells must line up
        1:1 with the sorted film_wells keys (from set_film_plate_16). Hovers
        over each spot for hover_seconds after dispensing so the drop has
        time to settle before the pipette moves on."""
        keys = sorted(film_wells.keys())
        if len(source_wells) != len(keys):
            raise ValueError(f"source_wells must have {len(keys)} items to match the film plate, got {len(source_wells)}")

        self.pip20.configure_nozzle_layout(**self._get_tips_config(1, tiprack))

        for well, key in zip(source_wells, keys):
            anchor, (ox, oy, oz) = film_wells[key]
            location = anchor.top(z=oz).move(Point(ox, oy, 0))

            self.pip20.pick_up_tip()
            self.pip20.aspirate(volume, well)
            self.pip20.move_to(location)
            self.pip20.dispense(volume)
            protocol.delay(seconds=hover_seconds)
            self.pip20.drop_tip()

    def test_film_plate_positions(
        self,
        protocol,
        plate_film,
        film_wells: Dict[int, Any],
        tiprack,
        hover_height: float = HOVER_HEIGHT,
        pause: bool = True,
    ) -> None:
        """Pick up a single tip and step through every film-plate spot, pausing at
        each one so the position can be checked against the physical hot plate
        before running a real drop cast. Tune the offsets in film_wells (from
        set_film_plate_16) between runs based on what you see. Set pause=False
        to just delay 3s at each spot instead of blocking for manual resume
        (e.g. for an unattended simulate/dry-run pass)."""
        self.pip20.configure_nozzle_layout(**self._get_tips_config(1, tiprack))
        self.pip20.pick_up_tip()

        for key in sorted(film_wells.keys()):
            anchor, (ox, oy, oz) = film_wells[key]
            location = anchor.top(z=hover_height + oz).move(Point(ox, oy, 0))
            self.pip20.move_to(location)
            if pause:
                protocol.pause(
                    f"Spot {key}/{len(film_wells)}: hovering at x={ox:.1f}, y={oy:.1f}, "
                    f"z={hover_height + oz:.1f} above A1. Check alignment, then resume."
                )
            else:
                protocol.delay(seconds=3)

        self.pip20.drop_tip()

def set_film_plate_16(
    protocol,
    slot,
    n_cols: int = GRID_COLS,
    n_rows: int = GRID_ROWS,
    pitch: float = GRID_PITCH,
    x_offset: float = GRID_X_OFFSET,
    y_offset: float = GRID_Y_OFFSET,
    z_offset: float = GRID_Z_OFFSET,
):
    """n_cols x n_rows (default 4x4, 16-spot) drop-cast grid, anchored off a PCR
    plate loaded in the given slot purely for a stable deck reference frame --
    there's no Opentrons labware definition for the hot plate itself, so
    set_offset plus x_offset/y_offset/z_offset are what actually align the grid
    to the physical plate. Row 0 sits at the anchor's A1; each following row
    steps forward (toward the front of the deck) by `pitch`.
    Use Quasi2DProtocol.test_film_plate_positions() (or dropcast_position.py) to
    dial these in. The plate sits on top of a heater, hence z=83 mm below.
    """
    if x_offset is None:
        x_offset = pitch / 2
    if y_offset is None:
        y_offset = pitch / 2

    plate_film = protocol.load_labware('opentrons_96_wellplate_200ul_pcr_full_skirt', slot)
    plate_film.set_offset(x=3, y=1.5, z=80)

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



def run(protocol):        
    # Working Layout
    '''
    [ 10 empty   ]  [ 11 empty   ]  [ trash  ]
    [  7 plate_96 ]  [  8 precursor_reservoir   ]  [  9 heater  ]
    [  4 empty    ]  [  5 empty   ]  [  6 film_plate on heater]
    [  1 tiprack_300 ]  [  2 tiprack_20  ]  [  3 heater ] ]

    '''
    # -----------------------
    # Tipracks — slot 2: tiprack_20, slot 3: tiprack_300
    # -----------------------
    tiprack_20 = protocol.load_labware("opentrons_96_tiprack_20ul", "2")
    tiprack_300 = protocol.load_labware("opentrons_96_tiprack_300ul", "1")

    # -----------------------
    # INSTRUMENT
    # -----------------------
    pip20 = protocol.load_instrument('p20_multi_gen2', mount='right', tip_racks=[tiprack_20])
    pip300 = protocol.load_instrument('p300_multi_gen2', mount='left', tip_racks=[tiprack_300])

    film = Quasi2DProtocol(pip300, pip20, fill_mode=FILL_MODE) # set class for quasi 2D protocol

    # -----------------------
    # Plates and Reservoirs — slot 5: plate_96, slot 6: reservoir, slot 7: film_plate
    # -----------------------
    plate_96 = protocol.load_labware("opentrons_96_wellplate_200ul_pcr_full_skirt", "7")
    plate_96.set_offset(x=0, y=0, z=5)

    plate_film, film_wells = set_film_plate_16(protocol, "6")

    reservoir = protocol.load_labware("opentrons_tough_4_reservoir_72ml", "8")
    reservoir.set_offset(x=0, y=0, z=5)

    # -----------------------
    # MAIN
    # -----------------------
    protocol.home()

    if TEST_FILM_PLATE_POSITIONS:
        protocol.comment("=== Film plate position check ===")
        film.test_film_plate_positions(protocol, plate_film, film_wells, tiprack_20)
        return

    protocol.comment(f"=== Loading Sample Parameters (mode: {FILL_MODE}) ===")
    samples = [SampleParameters(**s) for s in SAMPLE_DATA]
    is_valid, msg = validate_sample_parameters(samples, fill_mode=FILL_MODE)
    if not is_valid:
        raise ValueError(msg)
    protocol.comment(f"Loaded {len(samples)} samples from JSON")

    # Each chunk is one column (8 samples) or row (12 samples) of plate_96 --
    # loop over every chunk so all samples get filled, not just the first one.
    n_per_chunk = 8 if FILL_MODE == "column" else 12
    n_chunks = -(-len(samples) // n_per_chunk)  # ceiling division

    protocol.comment("=== Starting film Protocol ===")

    pbi2 = get_precursor("PbI2")
    baac = get_precursor("BAAc")
    mai = get_precursor("MAI")

    # Concatenate every chunk's wells/volumes/cycles into one flat, 16-long
    # list per precursor -- so each transfer step picks up tips once and
    # fills all 16 wells in a single pass, instead of re-picking tips per
    # plate column.
    dest_wells_all: list = []
    vol_pbi2_list: List[float] = []
    vol_baac_list: List[float] = []
    vol_mai_list: List[float] = []
    for fill_index in range(n_chunks):
        dest_wells_all += film._get_wells(plate_96, fill_index)
        p, b, m = samples_to_volume_lists(samples, fill_mode=FILL_MODE, index=fill_index)
        vol_pbi2_list += p
        vol_baac_list += b
        vol_mai_list += m

    if should_run(f"Step 1.1: transferring {pbi2.name}", RUN_TRANSFER_PBI2):
        film.transfer_precursor_batch(dest_wells_all, vol_pbi2_list, reservoir, tiprack_300, source_well_index=pbi2.well_index)
        protocol.comment(f"Transfer {pbi2.name} completed!")
    else:
        protocol.comment(f"Skipped {pbi2.name} transfer")

    if should_run(f"Step 1.2: transferring {baac.name}", RUN_TRANSFER_BAAC):
        film.transfer_precursor_batch(dest_wells_all, vol_baac_list, reservoir, tiprack_300, source_well_index=baac.well_index)
        protocol.comment(f"Transfer {baac.name} completed!")
    else:
        protocol.comment(f"Skipped {baac.name} transfer")

    if should_run(f"Step 1.3: transferring {mai.name}", RUN_TRANSFER_MAI):
        film.transfer_precursor_batch(dest_wells_all, vol_mai_list, reservoir, tiprack_300, source_well_index=mai.well_index)
        protocol.comment(f"Transfer {mai.name} completed!")
    else:
        protocol.comment(f"Skipped {mai.name} transfer")

    # Mixing uses a full 8-tip column pipette (style=ALL), which is physically
    # fixed to one plate column at a time -- it can't span two columns with
    # the same tips, so this still loops (and re-picks tips) per chunk.
    if should_run("Step 2: mixing", RUN_MIXING):
        for fill_index in range(n_chunks):
            film.mix_wells_column(plate_96, MIX_CYCLES, tiprack_300, mix_volume=50, dest_index=fill_index)
        protocol.comment("Mixing completed!")
    else:
        protocol.comment("Skipped mixing")

    if should_run("Step 3: drop casting", RUN_DROP_CASTING):
        source_wells = plate_96.columns()[0] + plate_96.columns()[1]  # 16 wells = sample_id 1-16
        film.drop_cast_single(protocol, source_wells, film_wells, tiprack_20, volume=DROP_VOL)
        protocol.comment("Drop casting completed!")
    else:
        protocol.comment("Skipped drop casting")

    protocol.comment("=== Protocol Complete ===")

