import json

# def get_values(*names):
#     _all_values = json.loads("""{
#         "input_csv": "sample_id,vol_a,vol_b,time,temperature\n1,100,50,30,25\n2,100,55,30,25\n3,105,50,35,25"
#     }""")
#     return [_all_values[n] for n in names]

# csv_raw = get_values("input_csv")[0]

SAMPLE_DATA = json.loads("""
[
    {"sample_id": 1, "vol_a": 100, "vol_b": 50, "time": 30, "temperature": 25},
    {"sample_id": 2, "vol_a": 100, "vol_b": 50, "time": 30, "temperature": 25},
    {"sample_id": 3, "vol_a": 80, "vol_b": 70, "time": 35, "temperature": 25},
    {"sample_id": 4, "vol_a": 80, "vol_b": 70, "time": 30, "temperature": 25},
    {"sample_id": 5, "vol_a": 60, "vol_b": 90, "time": 30, "temperature": 25},
    {"sample_id": 6, "vol_a": 60, "vol_b": 90, "time": 35, "temperature": 25},
    {"sample_id": 7, "vol_a": 40, "vol_b": 110, "time": 30, "temperature": 25},
    {"sample_id": 8, "vol_a": 40, "vol_b": 110, "time": 35, "temperature": 25}
]
""")

# "row"    → fill across a single row  (A1–A12), max 12 samples
# "column" → fill down a single column (A1–H1),  max 8 samples
FILL_MODE = "column" 

# Which row (0-indexed) or column (0-indexed) to target
FILL_INDEX = 0

"""
MOF Protocol: Full workflow for transfer, mix, and drop-cast operations.

This is the main protocol entry point for the Opentrons Flex.
"""
"""
CSV loader for MOF sample parameters.

Reads sample-specific parameters (volumes, times, temperatures) from a CSV file
and provides structured access to them during the protocol run.
"""
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

_labware_candidates = [Path("single_bundle_6_channel.json"), Path("custom_labware/single_bundle_6_channel.json")]
try:
    _here = Path(__file__).parent
    _labware_candidates += [
        _here / "single_bundle_6_channel.json",
        _here / "custom_labware" / "single_bundle_6_channel.json",
        _here.parent / "custom_labware" / "single_bundle_6_channel.json",
    ]
except NameError:
    pass
for _p in _labware_candidates:
    if _p.exists():
        with open(_p) as f:
            labware_def = json.load(f)
        break
else:
    raise FileNotFoundError("single_bundle_6_channel.json not found")

@dataclass
class SampleParameters:
    """Container for a single sample's parameters."""
    sample_id: int
    vol_a: float  # Volume of precursor A in µL
    vol_b: float  # Volume of precursor B in µL
    time: float   # Mixing time in seconds
    temperature: float  # Temperature in °C


def load_sample_parameters(csv_path: str) -> List[SampleParameters]:
    """
    Load sample parameters from a CSV file.
    
    Expected CSV format:
        sample_id,vol_a,vol_b,time,temperature
        1,100,50,30,25
        2,100,55,30,25
        ...
    
    Args:
        csv_path: Path to CSV file (relative or absolute)
    
    Returns:
        List of SampleParameters objects (one per sample)
    
    Raises:
        FileNotFoundError: If CSV file doesn't exist
        ValueError: If CSV format is invalid
    """
    csv_file = Path(csv_path)
    
    if not csv_file.exists():
        raise FileNotFoundError(f"Sample parameters CSV not found: {csv_path}")
    
    samples = []
    
    try:
        with open(csv_file, "r") as f:
            reader = csv.DictReader(f)
            
            if not reader.fieldnames:
                raise ValueError("CSV file is empty")
            
            required_fields = {"sample_id", "vol_a", "vol_b", "time", "temperature"}
            missing_fields = required_fields - set(reader.fieldnames or [])
            
            if missing_fields:
                raise ValueError(
                    f"CSV missing required columns: {missing_fields}. "
                    f"Found: {reader.fieldnames}"
                )
            
            for row_num, row in enumerate(reader, start=2):  # Start at 2 (header is row 1)
                try:
                    sample = SampleParameters(
                        sample_id=int(row["sample_id"]),
                        vol_a=float(row["vol_a"]),
                        vol_b=float(row["vol_b"]),
                        time=float(row["time"]),
                        temperature=float(row["temperature"]),
                    )
                    samples.append(sample)
                except (ValueError, KeyError) as e:
                    raise ValueError(f"Error parsing row {row_num}: {e}")
    
    except csv.Error as e:
        raise ValueError(f"CSV parsing error: {e}")
    
    if not samples:
        raise ValueError("CSV file contains no sample data rows")
    
    if len(samples) > 12:
        raise ValueError(f"CSV contains {len(samples)} samples, but only 12 samples are supported")
    
    return samples

def validate_sample_parameters(samples, fill_mode: str = "row") -> tuple[bool, str]:
    """Validate sample parameters (dict-based version)."""
    max_samples = 8 if fill_mode == "column" else 12

    if not samples:
        return False, "No samples provided"

    if len(samples) > max_samples:
        return False, f"Too many samples for {fill_mode} mode: {len(samples)} (max {max_samples})"

    for sample in samples:
        vol_a = sample["vol_a"]
        vol_b = sample["vol_b"]
        time = sample["time"]
        temp = sample["temperature"]
        sid = sample["sample_id"]

        if vol_a < 0 or vol_a > 200:
            return False, f"Sample {sid}: vol_a must be 0-200 µL, got {vol_a}"

        if vol_b < 0 or vol_b > 200:
            return False, f"Sample {sid}: vol_b must be 0-200 µL, got {vol_b}"

        if time < 0 or time > 300:
            return False, f"Sample {sid}: time must be 0-300s, got {time}"

        if temp < 0 or temp > 100:
            return False, f"Sample {sid}: temperature must be 0-100°C, got {temp}"

    return True, "All samples valid"


def samples_to_volume_lists(samples, fill_mode: str = "row") -> tuple[list[float], list[float]]:
    """Convert dict-based sample parameters to volume lists."""
    n = 8 if fill_mode == "column" else 12

    vol_a_list = [s["vol_a"] for s in samples]
    vol_b_list = [s["vol_b"] for s in samples]

    while len(vol_a_list) < n:
        vol_a_list.append(0)
    while len(vol_b_list) < n:
        vol_b_list.append(0)

    return vol_a_list[:n], vol_b_list[:n]

def samples_to_mix_cycles(samples, cycles_per_second: int = 3, fill_mode: str = "row") -> list[int]:
    """Convert sample times to mix cycles for each well (dict-based version)."""
    n = 8 if fill_mode == "column" else 12

    mix_cycles_list = [
        max(1, int(s["time"] * cycles_per_second / 10))
        for s in samples
    ]

    while len(mix_cycles_list) < n:
        mix_cycles_list.append(0)

    return mix_cycles_list[:n]


requirements = {"robotType": "OT-2", "apiLevel": "2.20"}

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
            return {"style": SINGLE, "tip_racks": [tiprack]}
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
        
        
    def transfer_precursor_multi(
        self,
        dest_plate,
        volumes: List[float],
        source_reservoir,
        tiprack,
        source_well_index: int = 0,
        dest_index: int = 0,
    ) -> None:
        """Transfer per-well volumes from one reservoir well to all destination wells."""
        if len(volumes) != self.n_wells:
            raise ValueError(f"volumes must be list of {self.n_wells} for {self.fill_mode} mode, got {len(volumes)}")

        self.pip300.configure_nozzle_layout(style=PARTIAL_COLUMN, start="H1", end="G1", tip_racks=[tiprack])

        source = source_reservoir.wells()[source_well_index]
        dest_wells = self._get_wells(dest_plate, dest_index)

        self.pip300.pick_up_tip()
        for well, vol in zip(dest_wells, volumes):
            if vol > 0:
                self.pip300.aspirate(vol, source)
                self.pip300.dispense(vol, well)
        self.pip300.drop_tip()

    def transfer_precursor_batch(self,
        dest_plate,
        volumes: List[float],
        source_reservoir,
        tiprack,
        source_well_index: int = 0,
        dest_index: int = 0,
        n: int = 2,
    ) -> None:
        """Transfer to first well of each n-well group, picking up tips at matching skip positions."""
        self.pip300.configure_nozzle_layout(**self._get_tips_config(n, tiprack))

        source = source_reservoir.wells()[source_well_index]
        dest_wells = self._get_wells(dest_plate, dest_index)
        tips = tiprack.columns()[0][n-1::n]  # B1, D1, F1, H1 for n=2

        for j, i in enumerate(range(0, len(volumes), n)):
            vol = volumes[i]
            if vol > 0:
                self.pip300.pick_up_tip(tips[j])
                self.pip300.aspirate(vol, source)
                self.pip300.dispense(vol, dest_wells[i + n - 1])
                self.pip300.drop_tip()

    def mix_wells_per_sample(
        self,
        dest_plate,
        mix_cycles_list: List[int],
        tiprack,
        mix_volume: float = 100,
        dest_index: int = 0,
    ) -> None:
        """Mix each well with per-sample cycle counts."""
        if len(mix_cycles_list) != self.n_wells:
            raise ValueError(f"mix_cycles_list must be {self.n_wells} items for {self.fill_mode} mode, got {len(mix_cycles_list)}")

        self.pip300.configure_nozzle_layout(style=PARTIAL_COLUMN, start="H1", end="G1", tip_racks=[tiprack])

        for well, cycles in zip(self._get_wells(dest_plate, dest_index), mix_cycles_list):
            if cycles > 0:
                self.pip300.pick_up_tip()
                self.pip300.mix(cycles, mix_volume, well)
                self.pip300.drop_tip()


    def mix_wells_column(
        self,
        dest_plate,
        mix_cycles_list: List[int],
        tiprack,
        mix_volume: float = 100,
        dest_index: int = 0,
    ) -> None:
        """Pick up a full column of tips and mix all 8 wells simultaneously."""
        if len(mix_cycles_list) != self.n_wells:
            raise ValueError(f"mix_cycles_list must be {self.n_wells} items for {self.fill_mode} mode, got {len(mix_cycles_list)}")

        self.pip300.configure_nozzle_layout(style=ALL, tip_racks=[tiprack])

        col_wells = self._get_wells(dest_plate, dest_index)
        cycles = max(mix_cycles_list)

        self.pip300.pick_up_tip()
        self.pip300.mix(cycles, mix_volume, col_wells[0])
        self.pip300.drop_tip()

    def drop_cast_multi(
        self,
        source_plate,
        dest_plate,
        tiprack,
        volume: float = 5,
        nwells: int = 8,
        n: int = 2,
    ) -> None:
        """Drop cast picking up 2 tips at a time, aspirating from first well of each pair."""
        self.pip20.configure_nozzle_layout(**self._get_tips_config(n, tiprack))
        src_cols = source_plate.columns()[:nwells]
        dst_cols = dest_plate.columns()[:nwells]
        tips = tiprack.columns()[0][n-1::n]  # B1, D1, F1, H1 for n=2

        for j, i in enumerate(range(0, nwells, n)):
            self.pip20.pick_up_tip(tips[j])
            self.pip20.aspirate(volume, src_cols[i + n - 1][0])
            self.pip20.dispense(volume, dst_cols[i + n - 1][0])
            self.pip20.drop_tip()

def set_custom_heater(protocol, slot):
    # heater offsets for dropcasting on to rectangle 12 samples
    # diameter o f96 = 7.0mm
    heater_plate = protocol.load_labware('opentrons_96_wellplate_200ul_pcr_full_skirt', slot)
    heater_plate.set_offset(x=-5, y=32, z=87) # Z lowered by 1 mm
    hs_offsets = {
        1: ('B2',  (-1.0,  +0.0 , -1.4)),
        2: ('B5',  (-1.0,  +0.0 , -1.4)),
        3: ('B8',  (-1.0,  +0.0 , -1.4)),
        4: ('B11', (-1.0,  +0.0 , -1.4)),
        5: ('E2',  (-1.0,  +0.0 , -1.4)),
        6: ('E5',  (-1.0,  +0.0 , -1.4)),
        7: ('E8',  (-1.0,  +0.0 , -1.4)),
        8: ('E11', (-1.0,  +0.0 , -1.4)),
        9: ('H2',  (-1.0,  -1.0 , -1.4)),
        10:('H5',  (-1.0,  -1.0 , -1.4)),
        11:('H8',  (-1.0,  -1.0 , -1.4)),
        12:('H11', (-1.0,  -1.0 , -1.4))
    }

    return heater_plate, hs_offsets


def run(protocol):
    # Working Layout
    '''
    [ 10 empty    ]  [ 11 empty    ]  [ trash  ]
    [  7 tiprack_300 ]  [  8 tiprack_20  ]  [  9 plate_film ]
    [  4 empty    ]  [  5 empty    ]  [  6 empty  ]
    [  1 reservoir ]  [  2 plate_96  ]  [  3 empty  ]

    '''

    # -----------------------
    # Tipracks — row 3: pickup A1-ref ~265mm, row 4 empty → within Y bounds
    # -----------------------
    tiprack_300 = protocol.load_labware("opentrons_96_tiprack_300ul", "7")
    tiprack_20 = protocol.load_labware("opentrons_96_tiprack_20ul", "8")

    # -----------------------
    # INSTRUMENT
    # -----------------------
    pip20 = protocol.load_instrument('p20_multi_gen2', mount='right', tip_racks=[tiprack_20])
    pip300 = protocol.load_instrument('p300_multi_gen2', mount='left', tip_racks=[tiprack_300])

    mof = Quasi2DProtocol(pip300, pip20, fill_mode=FILL_MODE)

    # -----------------------
    # Plates and Reservoirs — row 1: A1-ref ~80-130mm, row 2 empty → safe
    # -----------------------
    plate_96 = protocol.load_labware("opentrons_96_wellplate_200ul_pcr_full_skirt", "2")
    plate_96.set_offset(x=0, y=0, z=3)

    plate_film, film_wells = set_custom_heater(protocol, '3')


    reservoir = protocol.load_labware_from_definition(labware_def, "1")
    reservoir.set_offset(x=0, y=0, z=5)

    # -----------------------
    # MAIN
    # -----------------------
    protocol.home()

    protocol.comment(f"=== Loading Sample Parameters (mode: {FILL_MODE}, index: {FILL_INDEX}) ===")
    try:
        samples = SAMPLE_DATA
        is_valid, msg = validate_sample_parameters(samples, fill_mode=FILL_MODE)
        if not is_valid:
            raise ValueError(msg)
        protocol.comment(f"Loaded {len(samples)} samples from JSON")
    except Exception as e:
        protocol.comment(f"ERROR: Failed to load samples: {str(e)}")
        raise

    vol_a_list, vol_b_list = samples_to_volume_lists(samples, fill_mode=FILL_MODE)
    mix_cycles_list = samples_to_mix_cycles(samples, cycles_per_second=2, fill_mode=FILL_MODE)

    protocol.comment("=== Starting MOF Protocol ===")

    protocol.comment("Step 1.1: Transferring precursor A sample-specific volumes...")
    mof.transfer_precursor_batch(plate_96, vol_a_list, reservoir, tiprack_300, source_well_index=0, dest_index=FILL_INDEX)
    protocol.comment("Transfer precursor A completed!")

    protocol.comment("Step 1.2: Transferring precursor B sample-specific volumes...")
    mof.transfer_precursor_batch(plate_96, vol_b_list, reservoir, tiprack_300, source_well_index=1, dest_index=FILL_INDEX)
    protocol.comment("Transfer precursor B completed!")

    protocol.comment("Step 2: Mixing samples with sample-specific parameters...")
    mof.mix_wells_column(plate_96, mix_cycles_list, tiprack_300, mix_volume=50, dest_index=FILL_INDEX)
    protocol.comment("Mixing completed!")

    protocol.comment("Step 3: Drop casting...")
    mof.drop_cast_multi(plate_96, plate_film, tiprack_20, volume=5)
    protocol.comment("Drop casting completed!")

    protocol.comment("=== Protocol Complete ===")

