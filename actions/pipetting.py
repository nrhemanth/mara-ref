# hardware/ot2_actions.py
#
# Liquid-handling actions for the OT-2.
# Inherits all robot state (labware, pipettes, tip tracking) from OT2Controller.
#
# Rule: if it calls pipette.aspirate / dispense / mix / move → it lives here.
#       if it calls protocol.load_labware / load_instrument   → it lives in ot2.py.

from hardware.ot2 import OT2Controller
from opentrons import protocol_api
from opentrons.types import Point


# Nozzle end positions for partial column pickup on 8-channel pipettes.
# Partial layout always starts from H1 (frontmost nozzle) and works upward.
# n_tips=8 → full column (use ALL layout, no partial needed)
_PARTIAL_NOZZLE_END = {
    1: "H1",  # SINGLE layout used instead — kept here for completeness
    2: "G1",
    3: "F1",
    4: "E1",
    5: "D1",
    6: "C1",
    7: "B1",
    8: None,  # full column
}


class OT2Pipetting(OT2Controller):
    """
    Liquid-handling primitives for the OT-2.
    Inherits all robot state from OT2Controller.

    Usage in protocol files:
        from hardware.ot2_actions import OT2Actions

        def run(protocol):
            robot = OT2Actions(protocol, "config/imod_config.yaml")
            robot.pick_up_tip(robot.pipleft)
            robot.aspirate(robot.pipleft, 10, robot.plate_96["A1"])
            robot.dispense(robot.pipleft, 10, robot.plate_96["B1"])
            robot.drop_tip(robot.pipleft)
    """

    # ------------------------------------------------------------------
    # Single-channel primitives
    # ------------------------------------------------------------------

    def aspirate(
        self,
        pipette: protocol_api.InstrumentContext,
        volume: float,
        well,
        bottom_clearance: float = 1.0,
    ):
        """Aspirate from a well at a given height above the bottom."""
        pipette.aspirate(volume, well.bottom(bottom_clearance))

    def dispense(
        self,
        pipette: protocol_api.InstrumentContext,
        volume: float,
        well,
        bottom_clearance: float = 1.0,
        offset: tuple = (0.0, 0.0, 0.0),
    ):
        """Dispense into a well with an optional (x, y, z) fine offset."""
        target = well.bottom(bottom_clearance).move(Point(*offset))
        pipette.dispense(volume, target)

    def blow_out(
        self,
        pipette: protocol_api.InstrumentContext,
        location=None,
    ):
        """Blow out residual liquid. Defaults to trash."""
        pipette.blow_out(location or self.trash)

    def mix(
        self,
        pipette: protocol_api.InstrumentContext,
        well,
        repetitions: int = 5,
        volume: float = None,
        bottom_clearance: float = 1.0,
        rate: float = 1.0,
    ):
        """Mix in place at the given well."""
        vol = volume or pipette.max_volume * 0.8
        pipette.mix(repetitions, vol, well.bottom(bottom_clearance), rate=rate)

    def delay(self, seconds: float):
        """Pause the protocol for a fixed duration."""
        self.protocol.delay(seconds=seconds)

    def move_to_top(
        self,
        pipette: protocol_api.InstrumentContext,
        well,
        clearance: float = 1.0,
    ):
        """Move pipette to the top of a well (useful for drip-off pauses)."""
        pipette.move_to(well.top(clearance))

    def touch_tip(
        self,
        pipette: protocol_api.InstrumentContext,
        well=None,
        speed: float = 60.0,
        v_offset: float = -1.0,
    ):
        """Touch tip against well walls to knock off droplets."""
        if well:
            pipette.touch_tip(well, speed=speed, v_offset=v_offset)
        else:
            pipette.touch_tip(speed=speed, v_offset=v_offset)

    def air_gap(
        self,
        pipette: protocol_api.InstrumentContext,
        volume: float,
        height: float = 5.0,
    ):
        """Aspirate an air gap above the current well to prevent dripping."""
        pipette.air_gap(volume=volume, height=height)

    # ------------------------------------------------------------------
    # 8-channel full column
    # ------------------------------------------------------------------

    def aspirate_row(
        self,
        pipette: protocol_api.InstrumentContext,
        volume: float,
        plate,
        column: int,
        bottom_clearance: float = 1.0,
    ):
        """
        Aspirate from a full column (8 wells) using an 8-channel pipette.
        column is 1-indexed (1 = wells A1–H1).

        Example:
            robot.aspirate_row(robot.pip300_multi, 100, robot.plate_96, column=1)
        """
        self._require_multi(pipette, "aspirate_row")
        top_well = plate.columns()[column - 1][0]
        pipette.aspirate(volume, top_well.bottom(bottom_clearance))

    def dispense_row(
        self,
        pipette: protocol_api.InstrumentContext,
        volume: float,
        plate,
        column: int,
        bottom_clearance: float = 1.0,
        offset: tuple = (0.0, 0.0, 0.0),
    ):
        """
        Dispense into a full column (8 wells) using an 8-channel pipette.
        column is 1-indexed (1 = wells A1–H1).

        Example:
            robot.dispense_row(robot.pip300_multi, 100, robot.plate_96, column=2)
        """
        self._require_multi(pipette, "dispense_row")
        top_well = plate.columns()[column - 1][0]
        target = top_well.bottom(bottom_clearance).move(Point(*offset))
        pipette.dispense(volume, target)

    def mix_row(
        self,
        pipette: protocol_api.InstrumentContext,
        plate,
        column: int,
        repetitions: int = 5,
        volume: float = None,
        bottom_clearance: float = 1.0,
        rate: float = 1.0,
    ):
        """
        Mix an entire column simultaneously using an 8-channel pipette.

        Example:
            robot.mix_row(robot.pip300_multi, robot.plate_96, column=3, repetitions=10)
        """
        self._require_multi(pipette, "mix_row")
        vol = volume or pipette.max_volume * 0.8
        top_well = plate.columns()[column - 1][0]
        pipette.mix(repetitions, vol, top_well.bottom(bottom_clearance), rate=rate)

    def transfer_row(
        self,
        pipette: protocol_api.InstrumentContext,
        volume: float,
        source_plate,
        source_column: int,
        dest_plate,
        dest_column: int,
        bottom_clearance: float = 1.0,
        touch_tip: bool = False,
        blow_out: bool = True,
    ):
        """
        Transfer a full column from one plate to another in a single move.
        Manages tip pickup and drop internally.

        Example:
            robot.transfer_row(
                robot.pip300_multi, volume=150,
                source_plate=robot.plate_96, source_column=1,
                dest_plate=dest_plate,       dest_column=3,
            )
        """
        self._require_multi(pipette, "transfer_row")
        src_well  = source_plate.columns()[source_column - 1][0]
        dest_well = dest_plate.columns()[dest_column - 1][0]

        self.pick_up_tip(pipette)
        pipette.aspirate(volume, src_well.bottom(bottom_clearance))
        pipette.dispense(volume, dest_well.bottom(bottom_clearance))

        if touch_tip:
            pipette.touch_tip()
        if blow_out:
            pipette.blow_out(self.trash)

        self.drop_tip(pipette)

    # ------------------------------------------------------------------
    # 8-channel partial column
    # ------------------------------------------------------------------

    def _configure_partial_column(
        self,
        pipette: protocol_api.InstrumentContext,
        n_tips: int,
        tiprack,
    ):
        """
        Configure an 8-channel pipette for partial column pickup.

        configure_nozzle_layout() resets the pipette's tip rack assignment,
        so tiprack must always be passed in to re-assign it.

        n_tips : 1–8
        tiprack: the tip rack labware to re-assign after reconfiguration
        """
        if not 1 <= n_tips <= 8:
            raise ValueError(f"n_tips must be 1–8, got {n_tips}.")

        if n_tips == 8:
            pipette.configure_nozzle_layout(
                style=protocol_api.ALL,
                start="A1",
                tip_racks=[tiprack],
            )
        elif n_tips == 1:
            pipette.configure_nozzle_layout(
                style=protocol_api.SINGLE,
                start="H1",
                tip_racks=[tiprack],
            )
        else:
            pipette.configure_nozzle_layout(
                style=protocol_api.PARTIAL_COLUMN,
                start="H1",
                end=_PARTIAL_NOZZLE_END[n_tips],
                tip_racks=[tiprack],
            )

    def aspirate_partial(
        self,
        pipette: protocol_api.InstrumentContext,
        volume: float,
        plate,
        column: int,
        n_tips: int = 8,
        bottom_clearance: float = 1.0,
        tiprack=None,
    ):
        """
        Aspirate from n_tips consecutive wells at the bottom of a column.

        The partial layout always starts at H1 (frontmost nozzle), so:
            n_tips=4 → aspirates from E1, F1, G1, H1
            n_tips=3 → aspirates from F1, G1, H1
            n_tips=8 → full column (same as aspirate_row)

        tiprack is required when n_tips != 8 because configure_nozzle_layout()
        resets the pipette's tip rack assignment.

        Example:
            robot.aspirate_partial(
                robot.pip300_multi, 100, robot.plate_96,
                column=1, n_tips=4, tiprack=robot.tiprack_300
            )
        """
        self._require_multi(pipette, "aspirate_partial")
        self._require_tiprack_for_partial(n_tips, tiprack)

        if n_tips != 8:
            self._configure_partial_column(pipette, n_tips, tiprack)

        col_wells  = plate.columns()[column - 1]  # [A, B, C, D, E, F, G, H]
        start_well = col_wells[8 - n_tips]        # n_tips=4 → index 4 → well E
        pipette.aspirate(volume, start_well.bottom(bottom_clearance))

    def dispense_partial(
        self,
        pipette: protocol_api.InstrumentContext,
        volume: float,
        plate,
        column: int,
        n_tips: int = 8,
        bottom_clearance: float = 1.0,
        offset: tuple = (0.0, 0.0, 0.0),
        tiprack=None,
    ):
        """
        Dispense into n_tips consecutive wells at the bottom of a column.
        Mirrors aspirate_partial() — same n_tips logic and well addressing.

        Example:
            robot.dispense_partial(
                robot.pip300_multi, 100, robot.plate_96,
                column=5, n_tips=3, tiprack=robot.tiprack_300
            )
            # dispenses into F5, G5, H5 simultaneously
        """
        self._require_multi(pipette, "dispense_partial")
        self._require_tiprack_for_partial(n_tips, tiprack)

        if n_tips != 8:
            self._configure_partial_column(pipette, n_tips, tiprack)

        col_wells  = plate.columns()[column - 1]
        start_well = col_wells[8 - n_tips]
        target = start_well.bottom(bottom_clearance).move(Point(*offset))
        pipette.dispense(volume, target)

    def restore_full_column(
        self,
        pipette: protocol_api.InstrumentContext,
        tiprack,
    ):
        """
        Restore an 8-channel pipette to full 8-tip mode after partial pickup.
        Always call this when you're done with partial operations.

        Example:
            robot.aspirate_partial(..., n_tips=4, tiprack=rack)
            robot.dispense_partial(..., n_tips=4, tiprack=rack)
            robot.restore_full_column(robot.pip300_multi, rack)
        """
        self._configure_partial_column(pipette, 8, tiprack)
        print(f"Restored {pipette.name} to full 8-channel mode.")

    # ------------------------------------------------------------------
    # Internal guards — keep error messages consistent
    # ------------------------------------------------------------------

    def _require_multi(
        self,
        pipette: protocol_api.InstrumentContext,
        method_name: str,
    ):
        """Raise if pipette is not one of the loaded 8-channel pipettes."""
        if pipette not in (self.pip20_multi, self.pip300_multi):
            raise ValueError(
                f"{method_name}() requires an 8-channel pipette "
                f"(pip20_multi or pip300_multi). "
                f"Use the single-channel equivalent for {pipette.name}."
            )

    def _require_tiprack_for_partial(self, n_tips: int, tiprack):
        """Raise if tiprack is missing for a partial pickup call."""
        if n_tips != 8 and tiprack is None:
            raise ValueError(
                "tiprack must be provided when n_tips != 8, because "
                "configure_nozzle_layout() resets the pipette's tip rack assignment."
            )
