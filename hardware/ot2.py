# hardware/ot2.py
#
# Low-level OT-2 hardware driver.
# This file knows HOW to move liquid — not WHAT experiment to run.
# Nothing in here should reference DataFrames, formulations,
# anneal times, or material-specific logic.

import yaml
from pathlib import Path

from opentrons import protocol_api
from opentrons.types import Location, Point

import pandas as pd
import numpy as np

# OT-2 8-channel pipette API load names (from Opentrons docs):
#   p20_multi_gen2   →  1–20 µL
#   p300_multi_gen2  →  20–300 µL
#
# Key behavioural difference vs single-channel:
#   The 8-channel always acts on a COLUMN of 8 wells simultaneously.
#   When you address well "A1", all 8 tips (A1–H1) move and pick up/
#   dispense together. You should always address by the TOP well of a
#   column (the "A" row), and the API handles the rest.
#
# Tip tracking for 8-channel:
#   A 96-well tiprack has 12 columns of 8 tips. After each pick_up_tip()
#   the rack advances by one full column (8 tips consumed). So a single
#   rack gives you 12 pick-ups, not 96.


class OT2Controller:
    """
    Hardware abstraction layer for the Opentrons OT-2.

    Responsibilities:
        - Instrument and labware initialisation
        - Tip lifecycle management
        - Raw aspirate / dispense / mix primitives
        - Heater module setup and control

    Not responsible for:
        - Deciding what volumes to dispense (that's modules/drop_casting.py)
        - Reading experiment DataFrames
        - Knowing about perovskites, annealing times, or formulations
    """
    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------
    def __init__(self, protocol: protocol_api.ProtocolContext, config_path: str = None):
        self.protocol = protocol
        self.protocol._commands.clear()

        # Empty until setup() is called
        self.labware          = {}
        self.pipettes         = {}
        self.pipleft      = None   # always set — whatever is on the left mount
        self.pipright     = None   # always set — whatever is on the right mount
        self.pip20        = None   # set only if p20_single_gen2 is loaded
        self.pip300       = None   # set only if p300_single_gen2 is loaded
        self.pip1000      = None   # set only if p1000_single_gen2 is loaded
        self.pip20_multi  = None   # set only if p20_multi_gen2 is loaded
        self.pip300_multi = None   # set only if p300_multi_gen2 is loaded
        self._tip_log         = {}
        self.heater_plate     = None
        self.heater_wells     = None
        self.heater_module    = None
        self.trash            = protocol.fixed_trash
        self.pipette_settings = {}

        if config_path is not None:
            self.setup(config_path)

    def setup(self, config_path: str):
        """
        Initialise the full OT-2 deck from a YAML config file.

        This replaces hard-coded labware/pipette loading in protocol files.
        Every project gets its own config YAML; the hardware code never changes.

        After calling setup(), the following are populated:
            self.labware        dict of role → labware object
            self.pipettes       dict of mount → pipette object
            self.pip20          convenience alias (if p20 single loaded)
            self.pip300         convenience alias (if p300 single loaded)
            self.pip20_multi    convenience alias (if p20 multi loaded)
            self.pip300_multi   convenience alias (if p300 multi loaded)
            self.heater_plate   loaded heater plate
            self.heater_wells   offset map {1: (well_name, (x,y,z)), ...}
            self.pipette_settings  dict of buffer/threshold values for modules

        Parameters
        ----------
        config_path : str
            Path to the project YAML config file.
            e.g. "config/imod_config.yaml"

        Example
        -------
        def run(protocol):
            robot = OT2Controller(protocol)
            robot.setup("config/imod_config.yaml")
        """
        config_path = Path(config_path)

        if not config_path.is_absolute():
            repo_root   = Path(__file__).resolve().parent.parent
            config_path = repo_root / config_path

        if not config_path.exists():
            raise FileNotFoundError(
                f"Config file not found: {config_path}\n"
                f"Repo root resolved to: {config_path.parent.parent}\n"
                f"Files found in config/: "
                f"{list((repo_root / 'config').glob('*.yaml'))}"
            )

        with open(config_path, "r") as f:
            cfg = yaml.safe_load(f)

        print(f"Loading config: {cfg.get('project', 'unnamed')} "
              f"by {cfg.get('author', 'unknown')}")

        # ── 1. Tip racks ────────────────────────────────────────────────
        # Build a slot → labware object map so pipettes can look up their rack.
        self._tipracks_by_slot = {}
        for tr in cfg.get("tipracks", []):
            rack = self.protocol.load_labware(tr["name"], tr["slot"])
            self._tipracks_by_slot[tr["slot"]] = rack
        print(f"  Loaded {len(self._tipracks_by_slot)} tip rack(s).")

        # ── 2. Pipettes ──────────────────────────────────────────────────
        self.labware   = {}   # role → labware object (filled in step 3)
        self.pipettes  = {}   # "left" / "right" → pipette object

        # Reset convenience aliases — will be set below as found
        self.pip20        = None
        self.pip300       = None
        self.pip20_multi  = None
        self.pip300_multi = None
        self._tip_log     = {}

        for pip_cfg in cfg.get("pipettes", []):
            slot   = pip_cfg["tiprack_slot"]
            rack   = self._tipracks_by_slot.get(slot)
            if rack is None:
                raise ValueError(
                    f"Pipette '{pip_cfg['api_name']}' references tiprack slot "
                    f"'{slot}', but no tiprack was loaded there. "
                    f"Check your tipracks section."
                )

            mount     = pip_cfg["mount"]           # "left" | "right"
            pip_type  = pip_cfg.get("type", "single")  # "single" | "multi"
            api_name  = pip_cfg["api_name"]

            pip = self.protocol.load_instrument(
                api_name, mount=mount, tip_racks=[rack]
            )

            # Apply flow rates from config
            fr = pip_cfg.get("flow_rates", {})
            if "aspirate" in fr:
                pip.flow_rate.aspirate = fr["aspirate"]
            if "dispense" in fr:
                pip.flow_rate.dispense = fr["dispense"]
            if "blow_out" in fr:
                pip.flow_rate.blow_out = fr["blow_out"]

            # Tip tracking:
            #   single → all 96 wells (individual tips)
            #   multi  → top row only (12 column pick-ups per rack)
            if pip_type == "multi":
                tips = rack.rows()[0]   # ["A1".."A12"] — one entry per column
            else:
                tips = rack.wells()     # all 96 wells

            self._tip_log[pip] = {"tips": tips, "next": 0}
            self.pipettes[mount] = pip

            # Mount-based (always set, model-agnostic)
            if mount == "left":  self.pipleft  = pip
            if mount == "right": self.pipright = pip

            # Model-based (only set if that specific pipette is loaded)
            if "p20_single"  in api_name: self.pip20        = pip
            if "p300_single" in api_name: self.pip300       = pip
            if "p1000_single"in api_name: self.pip1000      = pip
            if "p20_multi"   in api_name: self.pip20_multi  = pip
            if "p300_multi"  in api_name: self.pip300_multi = pip

            print(f"  Loaded {api_name} on {mount} mount "
                  f"({pip_type}, rack slot {slot}).")

        # ── 3. Labware ───────────────────────────────────────────────────
        for lw_cfg in cfg.get("labware", []):
            role = lw_cfg["role"]

            # "wells" entries are plain lists, not actual labware
            if "wells" in lw_cfg and "name" not in lw_cfg:
                self.labware[role] = lw_cfg["wells"]
                print(f"  Registered well list '{role}': {lw_cfg['wells']}")
                continue

            lw = self.protocol.load_labware(lw_cfg["name"], lw_cfg["slot"])

            offset = lw_cfg.get("offset", [0, 0, 0])
            lw.set_offset(x=offset[0], y=offset[1], z=offset[2])

            self.labware[role] = lw

            # Populate named shortcuts for commonly used plates
            if role == "mixing_plate": self.plate_96  = lw
            if role == "source_plate": self.plate_24  = lw

            print(f"  Loaded labware '{role}' "
                  f"({lw_cfg['name']}) in slot {lw_cfg['slot']} "
                  f"offset={offset}.")

        # ── 4. Heater ────────────────────────────────────────────────────
        heater_cfg = cfg.get("heater")
        if heater_cfg:
            slot        = heater_cfg["slot"]
            heater_type = heater_cfg["type"]

            if heater_type == "custom":
                plate = self.protocol.load_labware(
                    "opentrons_96_wellplate_200ul_pcr_full_skirt", slot
                )
                plate.set_offset(x=-5, y=32, z=87)
                self.heater_plate = plate
                self.heater_wells = {
                    int(k): (v[0], tuple(v[1]))
                    for k, v in heater_cfg["custom_offsets"].items()
                }

            elif heater_type == "opentrons":
                module  = self.protocol.load_module("heaterShakerModuleV1", slot)
                adapter = module.load_adapter("opentrons_universal_flat_adapter")
                plate   = adapter.load_labware("corning_384_wellplate_112ul_flat")
                self.heater_module = module
                self.heater_plate  = plate
                self.heater_wells  = {
                    int(k): (v[0], tuple(v[1]))
                    for k, v in heater_cfg["opentrons_offsets"].items()
                }

            else:
                raise ValueError(f"Unknown heater type '{heater_type}'. Use 'custom' or 'opentrons'.")

        # ── 5. Pipette settings (for use by modules, not hardware) ───────
        self.pipette_settings = cfg.get("pipette_settings", {})

        # ── 6. Trash ─────────────────────────────────────────────────────
        self.trash = self.protocol.fixed_trash

        # ── 7. Home ──────────────────────────────────────────────────────
        self.home()
        print(self.deck_snapshot())
        print(f"Setup complete for project '{cfg.get('project', 'unnamed')}'.")


    # ------------------------------------------------------------------
    # Debug helpers
    # ------------------------------------------------------------------

    def home(self):
        """Home both pipettes."""
        self.pipleft.home()
        self.pipright.home()
        #self.protocol.home()
        

    def print_cmd(self):
        """Print all queued protocol commands (useful for dry-run inspection)."""
        for cmd in self.protocol.commands():
            print(cmd)

    def clear_cmd(self):
        """Clear the protocol command buffer."""
        self.protocol._commands.clear()

    def drop_all_tips(self):
        """Drop all tips from both pipettes."""
        self.pip300.drop_tip()
        self.pip20.drop_tip()
    
    # ------------------------------------------------------------------
    # Deck inspection
    # ------------------------------------------------------------------
    def deck_snapshot(self):
        """
        Return a sorted list of (slot, labware_name, display_name) for all
        loaded labware, and raise a DeckOverlapError if any slot is doubled.
        """
        items = []
        seen_slots = {}

        for slot in self.protocol.deck:
            lw = self.protocol.deck[slot]
            if lw is None:
                continue

            load_name    = getattr(lw, "load_name",    str(lw))
            display_name = getattr(lw, "display_name", "")

            # Overlap check — the Opentrons API normally prevents this,
            # but catches any edge cases (e.g. modules + labware on same slot)
            if slot in seen_slots:
                raise DeckOverlapError(
                    f"Slot {slot} has multiple items: "
                    f"'{seen_slots[slot]}' and '{load_name}'. "
                    f"Check your config file for duplicate slot assignments."
                )
            seen_slots[slot] = load_name
            items.append((str(slot), load_name, display_name))

        return sorted(items, key=lambda x: int(x[0]) if x[0].isdigit() else 99)
    
    def validate_config_slots(self, cfg: dict):
        """
        Pre-flight check: scan the config for duplicate slot assignments
        BEFORE loading anything onto the robot.
        Call this at the top of setup() to catch errors early.
        """
        slot_registry = {}   # slot → what claimed it
        errors = []

        for tr in cfg.get("tipracks", []):
            slot = str(tr["slot"])
            if slot in slot_registry:
                errors.append(
                    f"Slot {slot}: tiprack '{tr['name']}' "
                    f"conflicts with '{slot_registry[slot]}'"
                )
            slot_registry[slot] = f"tiprack:{tr['name']}"

        for lw in cfg.get("labware", []):
            if "slot" not in lw:
                continue
            slot = str(lw["slot"])
            if slot in slot_registry:
                errors.append(
                    f"Slot {slot}: labware '{lw['name']}' (role: {lw['role']}) "
                    f"conflicts with '{slot_registry[slot]}'"
                )
            slot_registry[slot] = f"labware:{lw['name']}"

        heater = cfg.get("heater", {})
        if heater:
            slot = str(heater.get("slot", ""))
            if slot in slot_registry:
                errors.append(
                    f"Slot {slot}: heater conflicts with '{slot_registry[slot]}'"
                )
            slot_registry[slot] = "heater"

        if errors:
            msg = "\n".join(f"  - {e}" for e in errors)
            raise DeckOverlapError(f"Config has slot conflicts:\n{msg}")

        print(f"  Config pre-flight OK — {len(slot_registry)} slots assigned, no overlaps.")
        return slot_registry


    def position_testing(self, source, destination, drop_volume=3):
        '''
        Perform dropcasting from 96-well to 384-well with manual tip tracking.
        mix_well: array of stock locations
        hs_well: array of well locations
        volume: integer volume, Recommended 2 µL
        '''

        sample_wells = source

        # destination is a list of integer keys: [1, 2, 3, ...]
        destinations = [self.hs_wells[d] for d in destination]  # each is (well_name, offset)

        aspirate_volume = drop_volume

        self.pip20.pick_up_tip()
        for src, (well_name, offset) in zip(sample_wells, destinations):
            self.pip20.aspirate(aspirate_volume, self.plate_24.wells_by_name()[src].bottom(1))
            self.pip20.dispense(drop_volume, self.hs_plate.wells_by_name()[well_name].bottom(0.01).move(Point(*offset)))
            self.protocol.delay(seconds=1)
        self.pip20.drop_tip()


class DeckOverlapError(Exception):
    """Raised when two labware items are assigned to the same deck slot."""
    pass