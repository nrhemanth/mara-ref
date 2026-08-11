import json

import csv
from pathlib import Path
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass
import os
from io import StringIO
from datetime import datetime, timedelta
import time
import threading

from opentrons.protocol_api import ProtocolContext, InstrumentContext
from typing import Dict, Any, List, Union
from opentrons import protocol_api
from opentrons.protocol_api import SINGLE, PARTIAL_COLUMN, ALL
from opentrons.types import Point


# ---------------------------------------------------------------------------
# Pickup timer -- inlined here (rather than imported from mara.utils) so this
# protocol file has no dependency on the rest of the repo being installed.
# Only tracks wall-clock time in this local Python process, so it's only
# meaningful when running via opentrons_execute with a terminal attached --
# not when uploaded through the Opentrons App.
# ---------------------------------------------------------------------------
active_timers = {}

class TimerThread(threading.Thread):
    def __init__(self, material_id, duration_min):
        super().__init__()
        self.material_id = material_id
        self.duration = timedelta(minutes=duration_min)
        self.start_time = datetime.now()
        self.end_time = self.start_time + self.duration

    def run(self):
        time.sleep(self.duration.total_seconds())
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Material {self.material_id} is done!")

def add_material(material_id, duration_min):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Timer started for {material_id} ({duration_min} min)")
    thread = TimerThread(material_id, duration_min)
    active_timers[material_id] = thread
    thread.start()


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

# Drop-casting volumes (µL)
ASPIRATE_VOL = 5    # how much to pull up from the 96-well plate
DROP_VOL     = 5  # how much to deposit on the substrate

# Number of mix strokes applied to each column during Step 2 mixing.
MIX_CYCLES = 20

# Film-plate drop-cast grid, tuned via dropcast_position.py's position-check script.
GRID_COLS = 4          # spots across (X) per row
GRID_ROWS = 4          # spots deep (Y), within the film plate's own footprint
GRID_PITCH = (115.0 - 22.0) / 3  # mm between adjacent spots -- 4x 22mm films spanning 12cm total edge-to-edge
GRID_X_OFFSET = None   # mm from anchor's A1 in X; None = center on GRID_PITCH
GRID_Y_OFFSET = None   # mm from anchor's A1 in Y; None = center on GRID_PITCH
GRID_Z_OFFSET = -11.5   # mm added to the heater-top Z (80 mm, set in set_film_plate_16) Set at -13.0 when glass + holder
HOVER_HEIGHT = 1.5     # mm above each spot to hover at for a visual check

 # Set True to jog the p20 (single tip) through all 16 film-plate spots, pausing at each one, instead of running the full protocol.
TEST_FILM_PLATE_POSITIONS = False

# Pre-set which steps to run. Edit these before uploading to the robot: on a
# real run through the Opentrons App there's no terminal for input() to read
# from, so these booleans are the only way to skip a step there.
RUN_TRANSFER_PBI2 = True
RUN_TRANSFER_BAAC = True
RUN_TRANSFER_MAI = True #True
RUN_MIXING = True
RUN_DROP_CASTING = False

# Well plate starting column
START_INDEX = 4  # 0-indexed plate column to start filling from (e.g. 2 = column 3, 4 = column 5, etc.) -- must be 0-11 and leave enough room for all samples to fit in the 12-column plate_96

# Batch data embedded verbatim from input/0713_batch_1.csv -- kept inline (rather
# than read from that path at run-time) because protocol files execute on the
# OT-2's onboard server, which has no access back to this repo's filesystem.
BATCH_CSV = """well,sample_id,Temperature_C,Anneal_Time_min,PbI2_stock_volume_uL,MAI_stock_volume_uL,BAAc_stock_volume_uL,R_PbI2,R_MAI,R_BAAc
1,70,60,52,141,107,1,2.7,2.05
2,70,60,52,141,107,1,2.7,2.05
3,70,60,62,83,155,1,1.35,2.5
4,70,60,62,83,155,1,1.35,2.5
5,70,50,67,98,135,1,1.45,2
6,70,50,67,98,135,1,1.45,2
7,70,50,95,10,195,1,0.1,2.05
8,70,50,95,10,195,1,0.1,2.05
9,70,45,83,71,146,1,0.85,1.75
10,70,45,83,71,146,1,0.85,1.75
11,70,25,44,137,119,1,3.1,2.7
12,70,25,44,137,119,1,3.1,2.7
13,70,25,60,156,84,1,2.6,1.4
14,70,25,60,156,84,1,2.6,1.4
15,70,10,143,43,114,1,0.3,0.8
16,70,10,143,43,114,1,0.3,0.8
"""

# change well index to change the well in the precusor reservoir. 
# default is 0,1,2
PRECURSORS = json.loads("""{
    "PbI2": {"name": "PbI2", "well_index": 9, "volume": 9500, "concentration": 1.0, "solvent": "DMF:DMSO"},
    "BAAc": {"name": "BAAc", "well_index": 10, "volume": 9500, "concentration": 1.0, "solvent": "DMF:DMSO"},
    "MAI":  {"name": "MAI",  "well_index": 11, "volume": 9500, "concentration": 1.0, "solvent": "DMF:DMSO"}
}
""")

# Opentrons API version requirements
requirements = {"robotType": "OT-2", "apiLevel": "2.27"}

def _load_sample_data_from_csv(csv_text: str) -> List[Dict[str, Any]]:
    """Parse a samples CSV (sample_id, Temperature_C, Anneal_Time_min,
    PbI2/MAI/BAAc_stock_volume_uL, R_* ratio columns) into SAMPLE_DATA's shape."""
    reader = csv.DictReader(StringIO(csv_text))
    return [
        {
            "sample_id": int(row["sample_id"]),
            "vol_PbI2": float(row["PbI2_stock_volume_uL"]),
            "vol_BAAc": float(row["BAAc_stock_volume_uL"]),
            "vol_MAI": float(row["MAI_stock_volume_uL"]),
            "temperature": float(row["Temperature_C"]),
            "anneal_min": float(row["Anneal_Time_min"]),
        }
        for row in reader
    ]

SAMPLE_DATA = _load_sample_data_from_csv(BATCH_CSV)

@dataclass
class SampleParameters:
    """Container for a single sample's parameters."""
    sample_id: int
    vol_PbI2: float  # Volume of PbI2 precursor in µL
    vol_BAAc: float  # Volume of BAAc precursor in µL
    vol_MAI: float   # Volume of MAI precursor in µL
    temperature: float  # Temperature in °C
    anneal_min: float  # How long after drop-casting this sample can be picked up, in minutes

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
def validate_sample_parameters(samples: List[SampleParameters]) -> Tuple[bool, str]:
    """Validate sample parameters."""
    if not samples:
        return False, "No samples provided"

    for sample in samples:
        vol_pbi2 = sample.vol_PbI2
        vol_baac = sample.vol_BAAc
        vol_mai = sample.vol_MAI
        temp = sample.temperature
        sid = sample.sample_id
        anneal_min = sample.anneal_min

        if vol_pbi2 < 0 or vol_pbi2 > 290:
            return False, f"Sample {sid}: vol_PbI2 must be 0-290 µL, got {vol_pbi2}"
        if vol_baac < 0 or vol_baac > 290:
            return False, f"Sample {sid}: vol_BAAc must be 0-290 µL, got {vol_baac}"
        if vol_mai < 0 or vol_mai > 290:
            return False, f"Sample {sid}: vol_MAI must be 0-290 µL, got {vol_mai}"
        if temp < 0 or temp > 150:
            return False, f"Sample {sid}: temperature must be 0-150°C, got {temp}"
        if anneal_min < 0 or anneal_min > 60:
            return False, f"Sample {sid}: anneal_min must be 0-60 min, got {anneal_min}"

    return True, "All samples valid"


def validate_batch_size(n: int) -> Tuple[bool, str]:
    """Drop-casting (and the paired-well precursor transfers) require an even
    batch size -- there's no fixed count like 16 otherwise."""
    if n <= 0 or n % 2 != 0:
        return False, f"Batch size must be a positive even number (dropcast in pairs), got {n}"
    return True, "batch size valid"


def validate_start_index(n_chunks: int, start_index: int = 0) -> Tuple[bool, str]:
    """Validate that start_index + n_chunks fits within plate_96's 12 columns."""
    max_slots = 12
    if start_index + n_chunks > max_slots:
        return False, (
            f"START_INDEX={start_index} + n_chunks={n_chunks} exceeds the "
            f"{max_slots} columns on plate_96"
        )
    return True, "start_index valid"

def samples_to_volume_lists(samples: List[SampleParameters], index: int = 0) -> Tuple[List[float], List[float], List[float]]:
    """Convert one plate column's worth of sample parameters to volume lists."""
    n = 8
    chunk = samples[index * n:(index + 1) * n]

    vol_pbi2_list = [s.vol_PbI2 for s in chunk]
    vol_baac_list = [s.vol_BAAc for s in chunk]
    vol_mai_list = [s.vol_MAI for s in chunk]

    for lst in (vol_pbi2_list, vol_baac_list, vol_mai_list):
        while len(lst) < n:
            lst.append(0)

    return vol_pbi2_list[:n], vol_baac_list[:n], vol_mai_list[:n]

#--- Functions for sample parameter validation and conversion ---#
class Quasi2DProtocol:
    def __init__(self, protocol, pip300, pip20):
        self.protocol = protocol
        self.pip300 = pip300
        self.pip20 = pip20
        self.n_wells = 8

    def _get_wells(self, plate, index: int = 0) -> list:
        """Return the target wells (one plate column) at the given index."""
        return plate.columns()[index]
    
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
        air_gap_vol: float = 5,
    ) -> None:
        """Transfer to the last well of each n-well group across dest_wells,
        picking up tips once and reusing them for the whole batch -- pass the
        full flat list of wells (e.g. spanning multiple plate columns) to fill
        them all in one pass instead of re-picking tips per column."""
        if len(volumes) != len(dest_wells):
            raise ValueError(f"volumes must match dest_wells length ({len(dest_wells)}), got {len(volumes)}")

        self.pip300.configure_nozzle_layout(**self._get_tips_config(n, tiprack))

        source = source_reservoir.wells()[source_well_index].bottom(z=-8) # aspirate from 8mm below the bottom of the reservoir well to avoid air aspiration

        self.pip300.pick_up_tip()
        for i in range(0, len(volumes), n):
            vol = volumes[i]
            if vol > 0:
                self.pip300.aspirate(vol, source)
                self.pip300.air_gap(air_gap_vol) # traps a pocket of air below the tip opening so residual liquid can't drip out between wells
                self.protocol.delay(seconds = 1) # to prevent dripping
                self.pip300.dispense(vol + air_gap_vol, dest_wells[i + n - 1].top(z=-3))
                self.pip300.blow_out(dest_wells[i + n - 1].top(z=-5)) # to prevent dripping
        self.pip300.drop_tip()

    def mix_wells_column(
        self,
        dest_plate,
        cycles: int,
        tiprack,
        mix_volume: float = 150,
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
        volume: float = 10,
        hover_seconds: float = 3,
        sample_ids: list = None,
        anneal_mins: list = None,
    ) -> None:
        """Drop cast one film-plate spot at a time: one source well per spot,
        one tip picked up and dropped per drop. source_wells must line up
        1:1 with the sorted film_wells keys (from set_film_plate_16). Hovers
        over each spot for hover_seconds after dispensing so the drop has
        time to settle before the pipette moves on.

        If sample_ids/anneal_mins are given (one entry per source well, same
        order), right after each sample's drop is dispensed this:
          1. starts a local background pickup timer (print-only; only visible
             when running via opentrons_execute with a terminal attached), and
          2. calls protocol.comment() with a TIMER_START marker, which IS
             visible remotely -- it shows up in this run's command list via
             the Opentrons HTTP API, which is how preruns/preflight_films.py
             computes each sample's pickup time from the instrument PC."""
        all_keys = sorted(film_wells.keys())
        if len(source_wells) % 2 != 0:
            raise ValueError(f"source_wells must be an even count (dropcast in pairs), got {len(source_wells)}")
        if len(source_wells) > len(all_keys):
            raise ValueError(f"source_wells has {len(source_wells)} items, exceeds the {len(all_keys)} spots on the film plate")
        keys = all_keys[:len(source_wells)]
        if sample_ids is not None and len(sample_ids) != len(source_wells):
            raise ValueError(f"sample_ids must have {len(source_wells)} items, got {len(sample_ids)}")
        if anneal_mins is not None and len(anneal_mins) != len(source_wells):
            raise ValueError(f"anneal_mins must have {len(source_wells)} items, got {len(anneal_mins)}")

        self.pip20.configure_nozzle_layout(**self._get_tips_config(1, tiprack))

        for i, (well, key) in enumerate(zip(source_wells, keys)):
            anchor, (ox, oy, oz) = film_wells[key]
            location = anchor.top(z=oz).move(Point(ox, oy, 0))

            self.pip20.pick_up_tip()
            self.pip20.aspirate(volume, well)
            self.pip20.move_to(location)
            self.pip20.dispense(volume)
            protocol.delay(seconds=hover_seconds)
            self.pip20.drop_tip()

            if sample_ids is not None and anneal_mins is not None:
                add_material(sample_ids[i], anneal_mins[i])
                protocol.comment(f"TIMER_START sample={sample_ids[i]} anneal_min={anneal_mins[i]}")

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
    [  7 precursor_reservoir  ]  [  8 plate_96  ]  [  9 heater  ]
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

    film = Quasi2DProtocol(protocol, pip300, pip20) # set class for quasi 2D protocol

    # -----------------------
    # Plates and Reservoirs — slot 5: plate_96, slot 6: reservoir, slot 7: film_plate
    # -----------------------
    plate_96 = protocol.load_labware("opentrons_96_wellplate_200ul_pcr_full_skirt", "8")
    plate_96.set_offset(x=0, y=0, z=5)

    plate_film, film_wells = set_film_plate_16(protocol, "6")

    #reservoir = protocol.load_labware("opentrons_tough_4_reservoir_72ml", "8")
    reservoir = protocol.load_labware("nest_12_reservoir_22ml", "7")
    reservoir.set_offset(x=0, y=0, z=5)

    # -----------------------
    # MAIN
    # -----------------------
    protocol.home()

    if TEST_FILM_PLATE_POSITIONS:
        protocol.comment("=== Film plate position check ===")
        film.test_film_plate_positions(protocol, plate_film, film_wells, tiprack_20)
        return

    protocol.comment("=== Loading Sample Parameters ===")
    samples = [SampleParameters(**s) for s in SAMPLE_DATA]
    is_valid, msg = validate_sample_parameters(samples)
    if not is_valid:
        raise ValueError(msg)
    protocol.comment(f"Loaded {len(samples)} samples from JSON")

    is_valid, msg = validate_batch_size(len(samples))
    if not is_valid:
        raise ValueError(msg)

    # Each chunk is one column (8 samples) of plate_96 -- loop over every
    # chunk so all samples get filled, not just the first one.
    n_per_chunk = 8
    n_chunks = -(-len(samples) // n_per_chunk)  # ceiling division

    is_valid, msg = validate_start_index(n_chunks, start_index=START_INDEX)
    if not is_valid:
        raise ValueError(msg)
    
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
    for i in range(n_chunks):
        fill_index = START_INDEX + i  # destination column on plate_96
        dest_wells_all += film._get_wells(plate_96, fill_index)
        p, b, m = samples_to_volume_lists(samples, index=i)  # source chunk, still 0-based
        vol_pbi2_list += p
        vol_baac_list += b
        vol_mai_list += m

    protocol.comment("=== Starting film Protocol ===")
    if RUN_TRANSFER_PBI2:
        film.transfer_precursor_batch(dest_wells_all, vol_pbi2_list, reservoir, tiprack_300, source_well_index=pbi2.well_index)
        protocol.comment(f"Transfer {pbi2.name} completed!")
    else:
        protocol.comment(f"Skipped {pbi2.name} transfer")

    if RUN_TRANSFER_BAAC:
        film.transfer_precursor_batch(dest_wells_all, vol_baac_list, reservoir, tiprack_300, source_well_index=baac.well_index)
        protocol.comment(f"Transfer {baac.name} completed!")
    else:
        protocol.comment(f"Skipped {baac.name} transfer")

    if RUN_TRANSFER_MAI:
        film.transfer_precursor_batch(dest_wells_all, vol_mai_list, reservoir, tiprack_300, source_well_index=mai.well_index)
        protocol.comment(f"Transfer {mai.name} completed!")
    else:
        protocol.comment(f"Skipped {mai.name} transfer")

    # Mixing uses a full 8-tip column pipette (style=ALL), which is physically
    # fixed to one plate column at a time -- it can't span two columns with
    # the same tips, so this still loops (and re-picks tips) per chunk.
    if RUN_MIXING:
        for i in range(n_chunks):
            film.mix_wells_column(plate_96, MIX_CYCLES, tiprack_300, mix_volume=50, dest_index=START_INDEX + i)
        protocol.comment("Mixing completed!")
    else:
        protocol.comment("Skipped mixing")

    if RUN_DROP_CASTING:
        source_wells = []
        for i in range(n_chunks):
            source_wells += film._get_wells(plate_96, START_INDEX + i)
        # Trim off the zero-padded tail wells (chunks are padded to full
        # 8-well columns above) so drop-casting only touches real samples.
        source_wells = source_wells[:len(samples)]
        sample_ids = [s.sample_id for s in samples]
        anneal_mins = [s.anneal_min for s in samples]
        film.drop_cast_single(protocol, source_wells, film_wells, tiprack_20, volume=DROP_VOL,
                               sample_ids=sample_ids, anneal_mins=anneal_mins)
        protocol.comment("Drop casting completed!")
    else:
        protocol.comment("Skipped drop casting")

    protocol.comment("=== Protocol Complete ===")

