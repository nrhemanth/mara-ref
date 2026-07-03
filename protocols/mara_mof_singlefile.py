import json
from dataclasses import dataclass
from typing import List

from opentrons.protocol_api import ProtocolContext, SINGLE, COLUMN

# ── Sample data ───────────────────────────────────────────────────────────────
# Replace this with get_values("input_csv") when running via the Opentrons App
SAMPLE_DATA = json.loads("""
[
    {"sample_id": 1, "vol_a": 100, "vol_b": 50, "time": 30, "temperature": 25},
    {"sample_id": 2, "vol_a": 100, "vol_b": 55, "time": 30, "temperature": 25},
    {"sample_id": 3, "vol_a": 105, "vol_b": 50, "time": 35, "temperature": 25}
]
""")

requirements = {"robotType": "Flex", "apiLevel": "2.20"}


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class SampleParameters:
    sample_id: int
    vol_a: float
    vol_b: float
    time: float
    temperature: float


# ── Data helpers ──────────────────────────────────────────────────────────────

def validate_sample_parameters(samples) -> tuple[bool, str]:
    if not samples:
        return False, "No samples provided"
    if len(samples) > 12:
        return False, f"Too many samples: {len(samples)} (max 12)"
    for s in samples:
        sid = s["sample_id"]
        if not (0 <= s["vol_a"] <= 200):
            return False, f"Sample {sid}: vol_a must be 0-200 µL, got {s['vol_a']}"
        if not (0 <= s["vol_b"] <= 200):
            return False, f"Sample {sid}: vol_b must be 0-200 µL, got {s['vol_b']}"
        if not (0 <= s["time"] <= 300):
            return False, f"Sample {sid}: time must be 0-300s, got {s['time']}"
        if not (0 <= s["temperature"] <= 100):
            return False, f"Sample {sid}: temperature must be 0-100°C, got {s['temperature']}"
    return True, "All samples valid"


def samples_to_volume_lists(samples) -> tuple[list[float], list[float]]:
    vol_a = [s["vol_a"] for s in samples]
    vol_b = [s["vol_b"] for s in samples]
    while len(vol_a) < 12:
        vol_a.append(0)
    while len(vol_b) < 12:
        vol_b.append(0)
    return vol_a[:12], vol_b[:12]


def samples_to_mix_cycles(samples, cycles_per_second: int = 3) -> list[int]:
    cycles = [max(1, int(s["time"] * cycles_per_second / 10)) for s in samples]
    while len(cycles) < 12:
        cycles.append(0)
    return cycles[:12]


# ── Protocol class ────────────────────────────────────────────────────────────

class MOFProtocol:
    def __init__(self, protocol: ProtocolContext):
        self.protocol = protocol
        self._load_labware()
        self._load_instruments()

    def _load_labware(self):
        p = self.protocol
        self.tiprack_single = p.load_labware("opentrons_flex_96_tiprack_200ul", "B1")
        self.tiprack_col    = p.load_labware("opentrons_flex_96_tiprack_200ul", "B3")
        self.plate_96       = p.load_labware("opentrons_96_wellplate_200ul_pcr_full_skirt", "D2")
        self.xrd_plate      = p.load_labware("corning_6_wellplate_16.8ml_flat", "D3")
        self.reservoir      = p.load_labware("corning_6_wellplate_16.8ml_flat", "D1")
        self.trash          = p.load_trash_bin("A3")

    def _load_instruments(self):
        self.pip96 = self.protocol.load_instrument(
            "flex_96channel_200",
            mount="left",
            tip_racks=[self.tiprack_single, self.tiprack_col],
        )

    def _configure_single_layout(self, tiprack=None) -> None:
        self.pip96.configure_nozzle_layout(
            style=SINGLE,
            start="H12",
            tip_racks=[tiprack or self.tiprack_single],
        )

    def _configure_column_layout(self, tiprack=None) -> None:
        self.pip96.configure_nozzle_layout(
            style=COLUMN,
            start="H12",
            tip_racks=[tiprack or self.tiprack_col],
        )

    def transfer_precursor(self, volumes: List[float], source_well_index: int = 0) -> None:
        if len(volumes) != 12:
            raise ValueError(f"volumes must be list of 12, got {len(volumes)}")
        source = self.reservoir.wells()[source_well_index]
        self.pip96.pick_up_tip()
        for well, vol in zip(self.plate_96.rows()[0], volumes):
            if vol > 0:
                self.pip96.aspirate(vol, source)
                self.pip96.dispense(vol, well)
        self.pip96.drop_tip()

    def mix_wells(self, mix_cycles_list: List[int], mix_volume: float = 50) -> None:
        if len(mix_cycles_list) != 12:
            raise ValueError(f"mix_cycles_list must be 12 items, got {len(mix_cycles_list)}")
        for well, cycles in zip(self.plate_96.rows()[0], mix_cycles_list):
            if cycles > 0:
                self.pip96.pick_up_tip()
                self.pip96.mix(cycles, mix_volume, well)
                self.pip96.drop_tip()

    def drop_cast(self, volume: float = 5, nwells: int = 3) -> None:
        src_wells = self.plate_96.wells()[:nwells]
        dst_wells = self.xrd_plate.wells()[:nwells]
        for src_well, dst_well in zip(src_wells, dst_wells):
            self.pip96.pick_up_tip()
            self.pip96.aspirate(volume, src_well)
            self.pip96.dispense(volume, dst_well)
            self.pip96.drop_tip()


# ── Entry point ───────────────────────────────────────────────────────────────

def run(protocol: ProtocolContext):
    protocol.home()

    protocol.comment("=== Loading Sample Parameters ===")
    samples = SAMPLE_DATA
    is_valid, msg = validate_sample_parameters(samples)
    if not is_valid:
        raise ValueError(msg)
    protocol.comment(f"Loaded {len(samples)} samples")

    vol_a_list, vol_b_list = samples_to_volume_lists(samples)
    mix_cycles_list = samples_to_mix_cycles(samples, cycles_per_second=2)

    mof = MOFProtocol(protocol)

    protocol.comment("=== Starting MOF Protocol ===")

    protocol.comment("Step 1.1: Transferring precursor A...")
    mof._configure_single_layout()
    mof.transfer_precursor(vol_a_list, source_well_index=0)
    protocol.comment("Transfer precursor A completed!")

    protocol.comment("Step 1.2: Transferring precursor B...")
    mof._configure_single_layout()
    mof.transfer_precursor(vol_b_list, source_well_index=1)
    protocol.comment("Transfer precursor B completed!")

    protocol.comment("Step 2: Mixing samples...")
    mof.mix_wells(mix_cycles_list, mix_volume=50)
    protocol.comment("Mixing completed!")

    protocol.comment("Step 3: Drop casting...")
    mof.drop_cast(volume=5)
    protocol.comment("Drop casting completed!")

    protocol.comment("=== Protocol Complete ===")
