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


requirements = {"robotType": "OT-2", "apiLevel": "2.20"}

FILL_MODE = "column"
FILL_INDEX = 0

SINGLE_BUNDLE_6_CHANNEL_DEF = {
    "ordering": [["A1"],["A2"],["A3"],["A4"],["A5"],["A6"]],
    "brand": {"brand": "amg", "brandId": []},
    "metadata": {"displayName": "single_bundle_6_channel", "displayCategory": "reservoir", "displayVolumeUnits": "µL", "tags": []},
    "dimensions": {"xDimension": 127, "yDimension": 86, "zDimension": 20},
    "wells": {
        "A1": {"depth": 18, "totalLiquidVolume": 9500, "shape": "rectangular", "xDimension": 10, "yDimension": 70, "x": 15, "y": 41, "z": 2},
        "A2": {"depth": 18, "totalLiquidVolume": 9500, "shape": "rectangular", "xDimension": 10, "yDimension": 70, "x": 35, "y": 41, "z": 2},
        "A3": {"depth": 18, "totalLiquidVolume": 9500, "shape": "rectangular", "xDimension": 10, "yDimension": 70, "x": 55, "y": 41, "z": 2},
        "A4": {"depth": 18, "totalLiquidVolume": 9500, "shape": "rectangular", "xDimension": 10, "yDimension": 70, "x": 75, "y": 41, "z": 2},
        "A5": {"depth": 18, "totalLiquidVolume": 9500, "shape": "rectangular", "xDimension": 10, "yDimension": 70, "x": 95, "y": 41, "z": 2},
        "A6": {"depth": 18, "totalLiquidVolume": 9500, "shape": "rectangular", "xDimension": 10, "yDimension": 70, "x": 115, "y": 41, "z": 2},
    },
    "groups": [{"metadata": {"wellBottomShape": "u"}, "wells": ["A1","A2"]}],
    "parameters": {"format": "irregular", "quirks": ["centerMultichannelOnWells", "touchTipDisabled"], "isTiprack": False, "isMagneticModuleCompatible": False, "loadName": "single_bundle_6_channel"},
    "namespace": "custom_beta",
    "version": 1,
    "schemaVersion": 2,
    "cornerOffsetFromSlot": {"x": 0, "y": 0, "z": 0},
}


@dataclass
class SampleParameters:
    """Container for a single sample's parameters."""
    sample_id: int
    vol_PbI2: float  # Volume of PbI2 precursor in µL
    vol_BAAc: float  # Volume of BAAc precursor in µL
    vol_MAI: float   # Volume of MAI precursor in µL
    time: float   # Mixing time in seconds
    temperature: float  # Temperature in °C


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


def samples_to_mix_cycles(samples: List[SampleParameters], cycles_per_second: int = 3, fill_mode: str = "row", index: int = 0) -> List[int]:
    """Convert one column/row's worth of sample times to mix cycles."""
    n = 8 if fill_mode == "column" else 12
    chunk = samples[index * n:(index + 1) * n]

    mix_cycles_list = [max(1, int(s.time * cycles_per_second / 10)) for s in chunk]

    while len(mix_cycles_list) < n:
        mix_cycles_list.append(0)

    return mix_cycles_list[:n]


def confirm_step(protocol: protocol_api.ProtocolContext, step_name: str) -> bool:
    """Pause the robot, then ask in the terminal whether to run the next step.

    protocol.pause() halts hardware motion and, on the Opentrons App, shows a
    Resume/Cancel prompt so the plate/tips/reservoirs can be inspected first
    (it does not let you change Python variables mid-run, just resume or stop).
    The y/n prompt below requires a live terminal attached to the process
    (e.g. `opentrons_execute`/`opentrons_simulate` run directly over SSH) --
    if the protocol is started purely from the Opentrons App, there is no
    stdin for input() to read, so after Resume this will hang forever
    waiting for an answer that can never arrive. Only use this entry point
    when you're running from a terminal.
    """
    protocol.pause(
        f"About to run {step_name}. Inspect the plate/tips/reservoirs if needed, "
        f"then press Resume to continue or Cancel/Stop to terminate the run."
    )
    while True:
        answer = input(f"Proceed with {step_name}? [y/n]: ").strip().lower()
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print("Please enter y or n.")

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
        if len(volumes) != self.n_wells:
            raise ValueError(f"volumes must be list of {self.n_wells} for {self.fill_mode} mode, got {len(volumes)}")

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

    def test_film_plate_positions(
        self,
        protocol,
        plate_film,
        film_wells: Dict[int, Any],
        tiprack,
        hover_height: float = 5.0,
    ) -> None:
        """Pick up a single tip and step through every film-plate spot, pausing at
        each one so the position can be checked against the physical hot plate
        before running a real drop cast. Tune the offsets in film_wells (from
        set_film_plate_16) between runs based on what you see."""
        self.pip20.configure_nozzle_layout(**self._get_tips_config(1, tiprack))
        self.pip20.pick_up_tip()

        for key in sorted(film_wells.keys()):
            anchor, (ox, oy, oz) = film_wells[key]
            location = anchor.top(z=hover_height + oz).move(Point(ox, oy, 0))
            self.pip20.move_to(location)
            protocol.pause(
                f"Spot {key}/{len(film_wells)}: hovering at x={ox:.1f}, y={oy:.1f}, "
                f"z={hover_height + oz:.1f} above A1. Check alignment, then resume."
            )

        self.pip20.drop_tip()

def set_film_plate_16(protocol, slot, pitch: float = 25.0, x_offset: float = None, y_offset: float = None, z_offset: float = -1.0):
    """4x4 (16-spot) drop-cast grid for a 100mm x 100mm hot plate, closest to the
    given slot. There's no Opentrons labware definition for the hot plate itself, so
    a PCR plate is loaded purely to get a stable deck reference frame — set_offset
    plus x_offset/y_offset/z_offset are what actually align the grid to the physical
    plate. Defaults center the 4x4 grid (25 mm pitch) on a 100 mm square.
    Use Quasi2DProtocol.test_film_plate_positions() to dial these in."""
    if x_offset is None:
        x_offset = pitch / 2
    if y_offset is None:
        y_offset = pitch / 2

    plate_film = protocol.load_labware('opentrons_96_wellplate_200ul_pcr_full_skirt', slot)
    plate_film.set_offset(x=0, y=0, z=0)

    anchor = plate_film['A1']
    film_wells = {}
    key = 1
    for row in range(4):
        for col in range(4):
            x = x_offset + col * pitch
            y = y_offset + row * pitch
            film_wells[key] = (anchor, (x, y, z_offset))
            key += 1
    return plate_film, film_wells

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
    [ 10 heater   ]  [ 11 heater   ]  [ trash  ]
    [  7 film_plate ]  [  8 heater  ]  [  9 heater  ]
    [  4 empty    ]  [  5 plate_96   ]  [  6 precursor reservoir ]
    [  1 empty ]  [  2 tiprack_20  ]  [  3 tiprack_300 ] ]

    '''

    # Set True to jog the p20 (single tip) through all 16 film-plate spots,
    # pausing at each one, instead of running the full protocol.
    TEST_FILM_PLATE_POSITIONS = False

    # -----------------------
    # Tipracks — slot 2: tiprack_20, slot 3: tiprack_300
    # -----------------------
    tiprack_20 = protocol.load_labware("opentrons_96_tiprack_20ul", "2")
    tiprack_300 = protocol.load_labware("opentrons_96_tiprack_300ul", "3")

    # -----------------------
    # INSTRUMENT
    # -----------------------
    pip20 = protocol.load_instrument('p20_multi_gen2', mount='right', tip_racks=[tiprack_20])
    pip300 = protocol.load_instrument('p300_multi_gen2', mount='left', tip_racks=[tiprack_300])

    film = Quasi2DProtocol(pip300, pip20, fill_mode=FILL_MODE)

    # -----------------------
    # Plates and Reservoirs — slot 5: plate_96, slot 6: reservoir, slot 7: film_plate
    # -----------------------
    plate_96 = protocol.load_labware("opentrons_96_wellplate_200ul_pcr_full_skirt", "5")
    plate_96.set_offset(x=0, y=0, z=3)

    plate_film, film_wells = set_film_plate_16(protocol, "7")

    reservoir = protocol.load_labware_from_definition(SINGLE_BUNDLE_6_CHANNEL_DEF, "6")
    reservoir.set_offset(x=0, y=0, z=5)

    # -----------------------
    # MAIN
    # -----------------------
    protocol.home()

    if TEST_FILM_PLATE_POSITIONS:
        protocol.comment("=== Film plate position check ===")
        film.test_film_plate_positions(protocol, plate_film, film_wells, tiprack_20)
        return

    protocol.comment(f"=== Loading Sample Parameters (mode: {FILL_MODE}, index: {FILL_INDEX}) ===")
    samples = [SampleParameters(**s) for s in SAMPLE_DATA]
    is_valid, msg = validate_sample_parameters(samples, fill_mode=FILL_MODE)
    if not is_valid:
        raise ValueError(msg)
    protocol.comment(f"Loaded {len(samples)} samples from JSON")

    vol_pbi2_list, vol_baac_list, vol_mai_list = samples_to_volume_lists(samples, fill_mode=FILL_MODE, index=FILL_INDEX)
    mix_cycles_list = samples_to_mix_cycles(samples, cycles_per_second=2, fill_mode=FILL_MODE, index=FILL_INDEX)

    protocol.comment("=== Starting film Protocol ===")

    if confirm_step(protocol, "Step 1.1: transferring PbI2"):
        film.transfer_precursor_batch(plate_96, vol_pbi2_list, reservoir, tiprack_300, source_well_index=0, dest_index=FILL_INDEX)
        protocol.comment("Transfer PbI2 completed!")
    else:
        protocol.comment("Skipped PbI2 transfer")

    if confirm_step(protocol, "Step 1.2: transferring BAAc"):
        film.transfer_precursor_batch(plate_96, vol_baac_list, reservoir, tiprack_300, source_well_index=1, dest_index=FILL_INDEX)
        protocol.comment("Transfer BAAc completed!")
    else:
        protocol.comment("Skipped BAAc transfer")

    if confirm_step(protocol, "Step 1.3: transferring MAI"):
        film.transfer_precursor_batch(plate_96, vol_mai_list, reservoir, tiprack_300, source_well_index=2, dest_index=FILL_INDEX)
        protocol.comment("Transfer MAI completed!")
    else:
        protocol.comment("Skipped MAI transfer")

    if confirm_step(protocol, "Step 2: mixing"):
        film.mix_wells_column(plate_96, mix_cycles_list, tiprack_300, mix_volume=50, dest_index=FILL_INDEX)
        protocol.comment("Mixing completed!")
    else:
        protocol.comment("Skipped mixing")

    if confirm_step(protocol, "Step 3: drop casting"):
        film.drop_cast_multi(plate_96, plate_film, tiprack_20, volume=5)
        protocol.comment("Drop casting completed!")
    else:
        protocol.comment("Skipped drop casting")

    protocol.comment("=== Protocol Complete ===")

