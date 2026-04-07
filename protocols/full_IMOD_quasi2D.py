# protocols/IMOD_quasi2D.py
#
# OT-2 protocol for the IMOD quasi-2D perovskite drop-casting project.
# Converted from Mara_Protocol_IMOD.ipynb.
#
# This file is the entry point for the Opentrons App.
# All hardware logic lives in hardware/ot2_actions.py.
# All experiment logic lives in modules/drop_casting.py.
#
# Run on robot:      upload this file to the Opentrons App
# Simulate locally:  opentrons_simulate protocols/IMOD_quasi2D.py

import pandas as pd
from opentrons.types import Point
from hardware.ot2_actions import OT2Actions

# ---------------------------------------------------------------------------
# Protocol metadata — read by the Opentrons App
# ---------------------------------------------------------------------------
metadata = {
    "protocolName": "IMOD Protocol",
    "author":       "Clara Tamura, Austin Martin",
    "description":  "Mara OT-2 Protocol for IMOD quasi-2D perovskite project",
    "apiLevel":     "2.19",
}

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
DROP_VOL     = 1.5  # how much to deposit on the substrate

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_conditions(url: str, n_samples: int = 12) -> pd.DataFrame:
    """
    Fetch the conditions CSV from the local HTTP server and return
    the last n_samples rows (the active sample set).
    Raises a clear error if the server is unreachable.
    """
    try:
        df = pd.read_csv(url)
    except Exception as e:
        raise RuntimeError(
            f"Could not load conditions from {url}.\n"
            f"Make sure the HTTP server is running:\n"
            f"  cd Mara_shared && python -m http.server 8000\n"
            f"Original error: {e}"
        )
    if len(df) < n_samples:
        raise ValueError(
            f"CSV has only {len(df)} rows — expected at least {n_samples}."
        )
    return df.tail(n_samples).reset_index(drop=True)


def distribute_solution(robot, df, column, source_well, tip_start="A1"):
    """
    Distribute one solution column from a 24-well source well into
    the destination wells on the 96-well plate.

    Batches aspirations to minimise tip changes:
    - Uses pipleft (p20) for volumes ≤ 20 µL
    - Uses pipright (p300) for volumes > 20 µL

    Parameters
    ----------
    robot       : OT2Actions instance
    df          : conditions DataFrame (must have 'well' and column columns)
    column      : CSV column name, e.g. "BAAc_vol"
    source_well : well ID on plate_24, e.g. "A1"
    tip_start   : tip rack well to start from, e.g. "A1" or "A5"
    """
    vols  = df[column].values.round(1)
    dests = df["well"].values

    if len(vols) != len(dests):
        raise ValueError("Volume list length must match number of destination wells.")

    pairs = list(zip(vols, dests))
    pip20_pairs  = [(v, d) for v, d in pairs if 1 <= v <= robot.pipleft.max_volume]
    pip300_pairs = [(v, d) for v, d in pairs if v > robot.pipleft.max_volume]

    def _batch_distribute(pipette, tiprack, pairs):
        """One tip, batched aspirations from source, dispense to each dest."""
        pipette.starting_tip = tiprack.wells_by_name()[tip_start]
        pipette.pick_up_tip()

        idx = 0
        while idx < len(pairs):
            batch, total = [], 0
            while idx < len(pairs):
                v, _ = pairs[idx]
                if total + v <= pipette.max_volume:
                    batch.append(pairs[idx])
                    total += v
                    idx += 1
                else:
                    break

            pipette.aspirate(total, robot.plate_24[source_well].bottom(1))
            pipette.move_to(robot.plate_24[source_well].top(1))
            robot.protocol.delay(seconds=2)

            for v, dest in batch:
                # Small x-offset keeps the tip out of any pooled liquid at centre
                pipette.dispense(
                    v,
                    robot.plate_96[dest].top().move(Point(x=2.0, y=0.0, z=-5))
                )

            pipette.blow_out(robot.trash)

        pipette.drop_tip()
        robot.clear_commands()

    if pip20_pairs:
        _batch_distribute(robot.pipleft, robot._tipracks_by_slot["11"], pip20_pairs)
    if pip300_pairs:
        _batch_distribute(robot.pipright, robot._tipracks_by_slot["10"], pip300_pairs)

    print(f"Distribution complete: {column} from {source_well}.")


def final_mix(robot, df):
    """
    Mix each destination well after all solutions have been distributed.
    Uses pipright (p300) with a fresh tip per well — 25 cycles × 200 µL.
    """
    print("Starting final mix...")
    well_names = df["well"].tolist()

    if len(well_names) > 96:
        raise ValueError("Cannot have more than 96 destination wells.")

    for well_name in well_names:
        well = robot.plate_96.wells_by_name()[well_name]
        robot.pipright.pick_up_tip()
        robot.pipright.mix(25, 200, well.bottom(1), rate=200)
        robot.pipright.drop_tip()

    print("Final mix complete.")


def mixing_sequence(robot, df, columns, tip_start="A1"):
    """
    Full distribution + final mix sequence.
    Distributes each solution from its source well, then mixes all wells.

    Source well order matches SOLUTION_COLUMNS order:
        A1 → columns[0] (BAAc)
        B1 → columns[1] (MAI)
        C1 → columns[2] (PbI2)
    """
    source_wells = robot.labware.get("source_wells", ["A1", "B1", "C1"])

    for source_well, column in zip(source_wells, columns):
        distribute_solution(robot, df, column, source_well, tip_start)

    final_mix(robot, df)


def dropcasting(robot, df, aspirate_vol=5, drop_vol=1.5):
    """
    Drop-cast from every well in the 96-well plate onto heater substrates.
    One fresh p20 tip per sample.

    Aspirates aspirate_vol µL, deposits drop_vol µL, pauses 1 s, drops tip.

    Parameters
    ----------
    df           : conditions DataFrame — must have 'well' and 'Anneal Time'
    aspirate_vol : µL to pull up
    drop_vol     : µL to deposit on substrate
    """
    if len(df) > len(robot.heater_wells):
        raise ValueError(
            f"Too many samples ({len(df)}). "
            f"Only {len(robot.heater_wells)} heater positions available."
        )

    sample_wells = df["well"].tolist()
    anneal_times = df["Anneal Time"].tolist()

    for i, (src_well, anneal_min) in enumerate(zip(sample_wells, anneal_times), start=1):
        if i not in robot.heater_wells:
            raise ValueError(f"No heater mapping for sample index {i}.")

        dest_well_name, offset = robot.heater_wells[i]

        robot.pipleft.pick_up_tip()
        robot.pipleft.aspirate(
            aspirate_vol,
            robot.plate_96.wells_by_name()[src_well].bottom(1)
        )
        robot.pipleft.dispense(
            drop_vol,
            robot.heater_plate.wells_by_name()[dest_well_name].bottom(0.05).move(Point(*offset))
        )
        robot.protocol.delay(seconds=1)
        robot.pipleft.drop_tip()

        print(f"[{i}] {src_well} → {dest_well_name}  |  "
              f"{drop_vol} µL deposited  |  anneal: {anneal_min} min")

    print("Dropcasting complete.")


def dropcast_manual(robot, source, destination, drop_vol=3):
    """
    Drop-cast from a manually specified list of source wells to heater positions.
    No DataFrame needed — useful for targeted re-casting or debugging.

    Parameters
    ----------
    source      : list of well names on plate_96, e.g. ['C11', 'C11', 'C11']
    destination : list of heater position keys (1–12), e.g. [1, 5, 9]
    drop_vol    : µL to deposit per well (default 3)

    Example (from notebook cell 11):
        dropcast_manual(robot, ['C11','C11','C11'], [1, 5, 9])
    """
    if len(source) != len(destination):
        raise ValueError("source and destination lists must be the same length.")

    aspirate_vol = drop_vol + 3  # extra volume to ensure full dispense

    for src_well, dest_idx in zip(source, destination):
        if dest_idx not in robot.heater_wells:
            raise ValueError(f"No heater mapping for destination index {dest_idx}.")

        dest_well_name, offset = robot.heater_wells[dest_idx]

        robot.pipleft.pick_up_tip()
        robot.pipleft.aspirate(
            aspirate_vol,
            robot.plate_96.wells_by_name()[src_well].bottom(1)
        )
        robot.pipleft.dispense(
            drop_vol,
            robot.heater_plate.wells_by_name()[dest_well_name].bottom(0.01).move(Point(*offset))
        )
        robot.protocol.delay(seconds=1)
        robot.pipleft.drop_tip()

        print(f"{src_well} → {dest_well_name} (pos {dest_idx})  |  {drop_vol} µL")


# ---------------------------------------------------------------------------
# Main protocol entry point — called by the Opentrons App
# ---------------------------------------------------------------------------

def run(protocol):
    """
    IMOD quasi-2D perovskite drop-casting protocol.

    Sequence
    --------
    1.  Initialise robot from config/imod_config.yaml
    2.  Load conditions CSV from lab network
    3.  Distribute BAAc, MAI, PbI2 into 96-well plate (batched, one tip per solution)
    4.  Final mix of all destination wells (fresh tip per well)
    5.  Drop-cast from 96-well plate onto heated substrates (fresh tip per sample)
    """

    # ── 1. Robot setup ───────────────────────────────────────────────────────
    robot = OT2Actions(protocol, "config/imod_config.yaml")

    # ── 2. Load experiment conditions ────────────────────────────────────────
    df = load_conditions(CONDITIONS_URL, n_samples=12)
    protocol.comment(f"Loaded {len(df)} samples.")
    protocol.comment(f"Wells: {df['well'].tolist()}")

    # ── 3 + 4. Distribute all solutions then mix ──────────────────────────────
    # BAAc from A1 → plate_96 wells
    # MAI  from B1 → plate_96 wells
    # PbI2 from C1 → plate_96 wells
    # Final mix: 25 × 200 µL per well
    mixing_sequence(
        robot,
        df,
        columns=SOLUTION_COLUMNS,
        tip_start=MIX_TIP_START,
    )

    # ── 5. Drop-cast onto heater substrates ──────────────────────────────────
    # Aspirate 5 µL per sample, deposit 1.5 µL, 1 s pause, drop tip.
    dropcasting(
        robot,
        df,
        aspirate_vol=ASPIRATE_VOL,
        drop_vol=DROP_VOL,
    )

    protocol.comment("IMOD protocol complete.")
