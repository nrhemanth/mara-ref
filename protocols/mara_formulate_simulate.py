import json

import csv
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass
from io import StringIO

from opentrons.protocol_api import RuntimeParameterRequiredError
from opentrons import protocol_api
from opentrons.protocol_api import SINGLE, PARTIAL_COLUMN, ALL


# ---------------------------------------------------------------------------
# Experiment parameters
# Anything you might want to change between runs lives here at the top,
# not buried in the run() function.
# ---------------------------------------------------------------------------

# Number of mix strokes applied to each column during Step 2 mixing.
MIX_CYCLES = 20

# transfer_precursor_batch's tip-engagement count, fixed -- NOT the same
# thing as how many unique wells are in a batch/column-chunk. Consecutive
# wells_in_order entries come in same-formulation repeat pairs (e.g.
# theoretical_stoichometry.csv: A2/B2 both get formulation #1's PbI2/MAI/BAAc
# ratios, C2/D2 formulation #2, E2/F2 formulation #3, G2/H2 formulation #4 --
# 4 formulations x 2 repeats = 8 unique wells). Passing this fixed pair size
# instead of the chunk's full length means the 2 engaged tips get reused
# across every pair in the chunk, aspirating each pair's own volume fresh
# from the shared reservoir well -- as opposed to engaging every tip in the
# chunk at once (a single ALL-style "whole row" pickup for an 8-well chunk),
# which only actually dispenses once, into the chunk's *last* well, using
# the *first* well's volume -- silently wrong (and empty) for every other
# well in the chunk. Only matters once a batch needs more than one pair
# (n_wells > PRECURSOR_PAIR_SIZE) -- smaller test batches that happened to
# have exactly PRECURSOR_PAIR_SIZE unique wells never exposed this.
PRECURSOR_PAIR_SIZE = 2

# Pre-set which steps to run. Edit these before uploading to the robot: on a
# real run through the Opentrons App there's no terminal for input() to read
# from, so these booleans are the only way to skip a step there.
RUN_TRANSFER_PBI2 = True
RUN_TRANSFER_MAI = True
RUN_TRANSFER_BAAC = True
RUN_MIXING = True

# Well plate starting column
START_INDEX = 2  # 0-indexed plate column to start filling from (e.g. 2 = column 3, 4 = column 5, etc.) -- must be 0-11 and leave enough room for all samples to fit in the 12-column plate_96

# Sample batch data (sample_id, film_num, film_well, well, anneal_time,
# anneal_temperature, hotcast_temperature, PbI2_vol, MAI_vol, BAAc_vol,
# PbI2_ratio, MAI_ratio, BAAc_ratio) comes from a CSV runtime parameter (see
# add_parameters below) instead of a pasted-in string -- pick a CSV in the
# Opentrons App/touchscreen at run setup, or point two_step_starter.py at
# one (it uploads it automatically). anneal_temperature/hotcast_temperature
# are two independent setpoints -- the external anneal hotplate's target and
# the internal/deck hotplate's target, respectively (see
# ot2/timers.py::anneal_heater_setpoint/hotcast_heater_setpoint, read by
# TwoStepSynthesisWorkflow before either OT2 upload -- this file's own run()
# doesn't set either itself). The same CSV also drives mara_drop_cast.py's
# run, uploaded as a separate protocol immediately after this one finishes --
# see workflows.py's TwoStepSynthesisWorkflow docstring.
# FALLBACK_BATCH_CSV is only ever read during parameter-less protocol
# analysis (e.g. right after upload, before a CSV is selected) -- see run()
# and the CSVParameter docs' RuntimeParameterRequiredError pattern. It is
# never used for an actual run.
FALLBACK_BATCH_CSV = """sample_id,film_num,film_well,well,anneal_time,anneal_temperature,hotcast_temperature,PbI2_vol,MAI_vol,BAAc_vol,PbI2_ratio,MAI_ratio,BAAc_ratio
TLALLD,1,A1,A2,15,105,80,60.0,120.0,120.0,1.0,2.0,2.0
ZPIPHZ,2,A2,A2,30,105,80,60.0,120.0,120.0,1.0,2.0,2.0
KRIPBB,3,A3,B2,15,105,80,60.0,120.0,120.0,1.0,2.0,2.0
XTLJUB,4,A4,B2,30,105,80,60.0,120.0,120.0,1.0,2.0,2.0
KABEUD,5,B1,C2,15,105,80,85.71,128.57,85.71,1.0,1.5,1.0
KUYWSD,6,B2,C2,30,105,80,85.71,128.57,85.71,1.0,1.5,1.0
RRTSGY,7,B3,D2,15,105,80,85.71,128.57,85.71,1.0,1.5,1.0
KTLGTW,8,B4,D2,30,105,80,85.71,128.57,85.71,1.0,1.5,1.0
THWIDG,9,C1,E2,15,105,80,100.0,133.3,66.7,1.0,1.333,0.667
RYDCRW,10,C2,E2,30,105,80,100.0,133.3,66.7,1.0,1.333,0.667
RPHAVJ,11,C3,F2,15,105,80,100.0,133.3,66.7,1.0,1.333,0.667
CWFDFT,12,C4,F2,30,105,80,100.0,133.3,66.7,1.0,1.333,0.667
UUMBHI,13,D1,G2,15,105,80,109.09,136.36,54.55,1.0,1.25,0.5
RKLYHC,14,D2,G2,30,105,80,109.09,136.36,54.55,1.0,1.25,0.5
KSVUCT,15,D3,H2,15,105,80,109.09,136.36,54.55,1.0,1.25,0.5
XKAEZG,16,D4,H2,30,105,80,109.09,136.36,54.55,1.0,1.25,0.5

"""

# change well index to change the well in the precusor reservoir.
# default is 0,1,2
PRECURSORS = json.loads("""{
    "PbI2": {"name": "PbI2", "well_index": 5, "volume": 9500, "concentration": 1.0, "solvent": "DMF:DMSO"},
    "MAI":  {"name": "MAI",  "well_index": 4, "volume": 9500, "concentration": 1.0, "solvent": "DMF:DMSO"},
    "BAAc": {"name": "BAAc", "well_index": 3, "volume": 9500, "concentration": 1.0, "solvent": "DMF:DMSO"}
}
""")

# Opentrons API version requirements
requirements = {"robotType": "OT-2", "apiLevel": "2.27"}


def add_parameters(parameters: protocol_api.ParameterContext) -> None:
    """Registers the batch_csv runtime parameter -- pick a CSV file for it
    in the Opentrons App/touchscreen at run setup (or via
    two_step_starter.py/MaraClient.upload_data_file + create_run's
    run_time_parameter_files, see mara_system/ot2/activities.py). Requires
    apiLevel >= 2.20 (this file declares 2.27)."""
    parameters.add_csv_file(
        variable_name="batch_csv",
        display_name="Batch CSV",
        # Opentrons rejects any CSV parameter description over 100
        # characters (ParameterNameError) -- the full column list
        # (sample_id,film_num,film_well,well,anneal_time,anneal_temperature,
        # hotcast_temperature,PbI2_vol,MAI_vol,BAAc_vol,PbI2_ratio,MAI_ratio,
        # BAAc_ratio) is well over 100 characters, so this is a shortened
        # human-readable summary instead.
        description="CSV with sample_id, well, anneal_time, anneal/hotcast temperature, and precursor volumes/ratios.",
    )


def _load_sample_data_from_csv(csv_text: str) -> List[Dict[str, Any]]:
    """Parse the batch CSV (ID, film_num, film_well, well, anneal_time,
    anneal_temperature, hotcast_temperature, PbI2_vol, MAI_vol, BAAc_vol,
    ...) into SampleParameters' shape. film_num/anneal_time/
    anneal_temperature/hotcast_temperature aren't used by this file's own
    run() (they only matter to TwoStepSynthesisWorkflow's own heater
    activation, and to mara_drop_cast.py's own copy of this same parser),
    but are parsed and validated here too since both files read the
    identical CSV independently -- see the module docstring's
    no-shared-dependency rationale."""
    reader = csv.DictReader(StringIO(csv_text))
    return [
        {
            "sample_id": row["sample_id"],
            "film_id": int(row["film_num"]),
            "well": row["well"],
            "anneal_temperature": float(row["anneal_temperature"]),
            "hotcast_temperature": float(row["hotcast_temperature"]),
            "anneal_min": float(row["anneal_time"]),
            "vol_PbI2": float(row["PbI2_vol"]),
            "vol_BAAc": float(row["BAAc_vol"]),
            "vol_MAI": float(row["MAI_vol"]),
        }
        for row in reader
    ]


@dataclass
class SampleParameters:
    """Container for a single sample's parameters."""
    sample_id: str
    film_id: int     # not used by this file's own run() -- kept so the CSV row shape/validation matches mara_drop_cast.py's, which does use it
    well: str        # source well label (e.g. "A1") -- samples sharing a well are drawn from the same physical precursor mix
    vol_PbI2: float  # Volume of PbI2 precursor in µL
    vol_BAAc: float  # Volume of BAAc precursor in µL
    vol_MAI: float   # Volume of MAI precursor in µL
    anneal_temperature: float  # External anneal hotplate target, °C -- not used by this file's own run(), see TwoStepSynthesisWorkflow
    hotcast_temperature: float  # Internal/deck hotplate target, °C -- see anneal_temperature
    anneal_min: float  # not used by this file's own run() -- see film_id

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
        anneal_temp = sample.anneal_temperature
        hotcast_temp = sample.hotcast_temperature
        sid = sample.sample_id
        anneal_min = sample.anneal_min

        if vol_pbi2 < 0 or vol_pbi2 > 290:
            return False, f"Sample {sid}: vol_PbI2 must be 0-290 µL, got {vol_pbi2}"
        if vol_baac < 0 or vol_baac > 290:
            return False, f"Sample {sid}: vol_BAAc must be 0-290 µL, got {vol_baac}"
        if vol_mai < 0 or vol_mai > 290:
            return False, f"Sample {sid}: vol_MAI must be 0-290 µL, got {vol_mai}"
        if anneal_temp < 0 or anneal_temp > 150:
            return False, f"Sample {sid}: anneal_temperature must be 0-150°C, got {anneal_temp}"
        if hotcast_temp < 0 or hotcast_temp > 150:
            return False, f"Sample {sid}: hotcast_temperature must be 0-150°C, got {hotcast_temp}"
        if anneal_min < 0 or anneal_min > 60:
            return False, f"Sample {sid}: anneal_min must be 0-60 min, got {anneal_min}"
        if sample.film_id < 1:
            return False, f"Sample {sid}: film_id must be >= 1, got {sample.film_id}"

    film_ids = [s.film_id for s in samples]
    dupes = sorted({fid for fid in film_ids if film_ids.count(fid) > 1})
    if dupes:
        return False, f"Duplicate film_ID(s) assigned to more than one sample: {dupes}"

    return True, "All samples valid"


def validate_wells_fit_column(n_wells: int, start_index: int = 0) -> Tuple[bool, str]:
    """Validate that the unique source wells fit in plate_96, spanning as
    many consecutive 8-row columns starting at start_index as needed --
    up to 2 columns (16 wells), since a batch can range from every film
    sharing one well up to every one of the 16 films having its own."""
    if start_index < 0 or start_index > 11:
        return False, f"START_INDEX must be 0-11, got {start_index}"
    if n_wells <= 0 or n_wells > 16:
        return False, f"Need 1-16 unique source wells (max 2 plate_96 columns), got {n_wells}"
    columns_needed = (n_wells + 7) // 8
    if start_index + columns_needed > 12:
        return False, (
            f"{n_wells} unique source wells need {columns_needed} plate_96 column(s) "
            f"starting at column {start_index + 1}, but only {12 - start_index} remain"
        )
    return True, "wells fit"


def group_samples_by_well(samples: List[SampleParameters]) -> List[str]:
    """Unique well labels in first-seen order (e.g. ["A1", "A2"]) -- each one
    is filled with precursor and mixed once."""
    return list(dict.fromkeys(s.well for s in samples))

#--- Formulation-only pipette helper ---#
class Quasi2DProtocol:
    def __init__(self, protocol, pip300):
        self.protocol = protocol
        self.pip300 = pip300
        self.n_wells = 8

    def _get_wells(self, plate, index: int = 0) -> list:
        """Return the target wells (one plate column) at the given index."""
        return plate.columns()[index]

    def _get_wells_multi(self, plate, start_index: int, n_wells: int) -> list:
        """Return n_wells destination wells, spanning as many consecutive
        plate_96 columns (8 rows each) starting at start_index as needed --
        e.g. 13 wells starting at column 0 returns all 8 wells of column 0
        plus the first 5 of column 1."""
        wells: list = []
        col = start_index
        while len(wells) < n_wells:
            wells.extend(self._get_wells(plate, col))
            col += 1
        return wells[:n_wells]

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
        elif n == 8:
            return {"style": ALL, "tip_racks": [tiprack]}
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

        source = source_reservoir.wells()[source_well_index].bottom(z=-4) # aspirate from 4mm below the bottom of the reservoir well to avoid air aspiration

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
        n: int = 8,
    ) -> None:
        """Pick up tips for `n` wells (default: a full 8-well column) and mix
        them simultaneously, `cycles` times. For n < 8 this configures a
        partial column the same way transfer_precursor_batch does, anchored
        at the group's last well (see _get_tips_config)."""
        col_wells = self._get_wells(dest_plate, dest_index)
        if n == 8:
            self.pip300.configure_nozzle_layout(style=ALL, tip_racks=[tiprack])
            anchor = col_wells[0]
        else:
            self.pip300.configure_nozzle_layout(**self._get_tips_config(n, tiprack))
            anchor = col_wells[n - 1]

        self.pip300.pick_up_tip()
        self.pip300.mix(cycles, mix_volume, anchor)
        self.pip300.drop_tip()


def run(protocol):
    # Working Layout (formulation only -- no film plate, no p20/tiprack_20;
    # see mara_drop_cast.py for the hot-cast step's own layout)
    '''
    [ 10 empty   ]  [ 11 empty   ]  [ trash  ]
    [  7 precursor_reservoir  ]  [  8 plate_96  ]  [  9 empty  ]
    [  4 empty    ]  [  5 empty   ]  [  6 empty ]
    [  1 empty    ]  [  2 empty   ]  [  3 tiprack_300 ] ]

    '''
    # -----------------------
    # Tipracks — slot 1: tiprack_300
    # -----------------------
    tiprack_300 = protocol.load_labware("opentrons_96_tiprack_300ul", "1")

    # -----------------------
    # INSTRUMENT
    # -----------------------
    pip300 = protocol.load_instrument('p300_multi_gen2', mount='left', tip_racks=[tiprack_300])

    film = Quasi2DProtocol(protocol, pip300) # set class for quasi 2D protocol

    # -----------------------
    # Plates and Reservoirs — slot 8: plate_96, slot 7: reservoir
    # -----------------------
    plate_96 = protocol.load_labware("opentrons_96_wellplate_200ul_pcr_full_skirt", "8")
    plate_96.set_offset(x=0, y=0, z=5)

    #reservoir = protocol.load_labware("opentrons_tough_4_reservoir_72ml", "8")
    reservoir = protocol.load_labware("nest_12_reservoir_22ml", "7")
    reservoir.set_offset(x=0, y=0, z=5)

    # -----------------------
    # MAIN
    # -----------------------
    protocol.comment("=== Loading Sample Parameters ===")
    try:
        batch_csv_text = protocol.params.batch_csv.contents
    except RuntimeParameterRequiredError:
        # No CSV selected yet -- only reachable during protocol analysis
        # (e.g. right after upload), never during an actual run. Falls back
        # to a single dummy row so analysis can complete; see add_parameters.
        protocol.comment("No batch CSV selected yet -- using fallback data for analysis")
        batch_csv_text = FALLBACK_BATCH_CSV
    sample_data = _load_sample_data_from_csv(batch_csv_text)
    samples = [SampleParameters(**s) for s in sample_data]
    is_valid, msg = validate_sample_parameters(samples)
    if not is_valid:
        raise ValueError(msg)
    protocol.comment(f"Loaded {len(samples)} samples from CSV")

    # Group samples by source well ("A1", "A2", ...) -- each unique well is
    # filled with precursor and mixed once, then mara_drop_cast.py's own run
    # draws repeatedly from that same physical well for every sample
    # assigned to it.
    wells_in_order = group_samples_by_well(samples)
    is_valid, msg = validate_wells_fit_column(len(wells_in_order), start_index=START_INDEX)
    if not is_valid:
        raise ValueError(msg)

    pbi2 = get_precursor("PbI2")
    mai = get_precursor("MAI")
    baac = get_precursor("BAAc")

    n_wells = len(wells_in_order)
    dest_wells = film._get_wells_multi(plate_96, START_INDEX, n_wells)

    def _volumes_by_well(attr: str) -> List[float]:
        # Every sample sharing a well must use the same stoichiometry, since
        # they're all drawn from that one physical mix -- take it from the
        # first sample seen for each well.
        return [getattr(next(s for s in samples if s.well == w), attr) for w in wells_in_order]

    vol_pbi2_list = _volumes_by_well("vol_PbI2")
    vol_mai_list = _volumes_by_well("vol_MAI")
    vol_baac_list = _volumes_by_well("vol_BAAc")

    # transfer_precursor_batch/mix_wells_column each move one physical
    # plate_96 column (<=8 rows) at a time via the 8-channel multi pipette --
    # chunk every list into per-column groups so a batch needing a second
    # column (>8 unique source wells) still works, one call per column.
    column_chunks = [(i, min(8, n_wells - i)) for i in range(0, n_wells, 8)]

    # Every chunk must be a whole number of repeat pairs -- see
    # PRECURSOR_PAIR_SIZE's own comment for why transfer_precursor_batch is
    # always called with that fixed size, not the chunk's own length.
    for _, length in column_chunks:
        if length % PRECURSOR_PAIR_SIZE != 0:
            raise ValueError(
                f"Column chunk of {length} unique well(s) isn't a whole number of "
                f"PRECURSOR_PAIR_SIZE ({PRECURSOR_PAIR_SIZE})-well repeat pairs -- "
                "every formulation is expected to repeat in pairs (see "
                "theoretical_stoichometry.csv). Adjust the batch CSV's well "
                "grouping, or PRECURSOR_PAIR_SIZE if the repeat count has changed."
            )

    protocol.comment("=== Starting Formulation Protocol ===")
    if RUN_TRANSFER_PBI2:
        for start, length in column_chunks:
            film.transfer_precursor_batch(
                dest_wells[start:start + length], vol_pbi2_list[start:start + length],
                reservoir, tiprack_300, source_well_index=pbi2.well_index, n=PRECURSOR_PAIR_SIZE,
            )
        protocol.comment(f"Transfer {pbi2.name} completed!")
    else:
        protocol.comment(f"Skipped {pbi2.name} transfer")

    if RUN_TRANSFER_MAI:
        for start, length in column_chunks:
            film.transfer_precursor_batch(
                dest_wells[start:start + length], vol_mai_list[start:start + length],
                reservoir, tiprack_300, source_well_index=mai.well_index, n=PRECURSOR_PAIR_SIZE,
            )
        protocol.comment(f"Transfer {mai.name} completed!")
    else:
        protocol.comment(f"Skipped {mai.name} transfer")

    if RUN_TRANSFER_BAAC:
        for start, length in column_chunks:
            film.transfer_precursor_batch(
                dest_wells[start:start + length], vol_baac_list[start:start + length],
                reservoir, tiprack_300, source_well_index=baac.well_index, n=PRECURSOR_PAIR_SIZE,
            )
        protocol.comment(f"Transfer {baac.name} completed!")
    else:
        protocol.comment(f"Skipped {baac.name} transfer")

    if RUN_MIXING:
        for column_offset, (start, length) in enumerate(column_chunks):
            film.mix_wells_column(
                plate_96, MIX_CYCLES, tiprack_300, mix_volume=150,
                dest_index=START_INDEX + column_offset, n=length,
            )
        protocol.comment("Mixing completed!")
    else:
        protocol.comment("Skipped mixing")

    protocol.comment("=== Formulation Complete -- leave plate_96 in place for mara_drop_cast.py ===")
