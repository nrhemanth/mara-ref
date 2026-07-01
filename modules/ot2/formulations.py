# modules/formulations.py
from Projects.Perovskite.hardware.ot2 import OT2Controller
from opentrons.types import Point
import pandas as pd
from opentrons.protocol_api import SINGLE, ALL

class Formulations(OT2Controller):
    def __init__(self, protocol, config_path=None):
        super().__init__(protocol, config_path)

    def mara_distribute_single(self, df: pd.DataFrame, variable, source_id, tip_start="A1"):
        """
        Distribute volumes from a source well into destination wells,
        batching aspirations to minimise tip changes.
        Uses pip20 for volumes ≤ 20 µL, pip300 for larger volumes.
        """
        vols  = df[variable].values.round(1)
        dests = df["well"].values

        if len(vols) != len(dests):
            raise ValueError("Volume list length must match number of destinations.")

        pairs        = list(zip(vols, dests))
        pip20_pairs  = [(v, d) for v, d in pairs if 1 <= v <= self.pipleft.max_volume]
        pip300_pairs = [(v, d) for v, d in pairs if v > self.pipleft.max_volume]

        tiprack_20  = self._tipracks_by_slot["11"]
        tiprack_300 = self._tipracks_by_slot["10"]

        def _distribute(pipette, pairs, tiprack):
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

                pipette.aspirate(total, self.plate_24[source_id].bottom(1))
                pipette.move_to(self.plate_24[source_id].top(1))
                self.protocol.delay(seconds=2)

                for v, d in batch:
                    pipette.dispense(
                        v,
                        self.plate_96[d].top().move(Point(x=2.0, y=0.0, z=-5))
                    )

                pipette.blow_out(self.trash)

            pipette.drop_tip()

        if pip20_pairs:
            _distribute(self.pipleft, pip20_pairs, tiprack_20)
        if pip300_pairs:
            _distribute(self.pipright, pip300_pairs, tiprack_300)

        print(f"Distribution complete: {variable} from {source_id}.")

    def final_mix_single(self, df: pd.DataFrame, tip_start=None):
        """Mix each destination well — 25 cycles × 200 µL, fresh tip per well."""
        if tip_start is not None:
            tiprack_300 = self._tipracks_by_slot["10"]
            self.pipright.starting_tip = tiprack_300.wells_by_name()[tip_start]

        well_names = df["well"].tolist()
        if len(well_names) > 96:
            raise ValueError("Cannot have more than 96 destination wells.")

        for name in well_names:
            well = self.plate_96.wells_by_name()[name]
            self.pipright.pick_up_tip()
            self.pipright.mix(25, 200, well.bottom(1), rate=200)
            self.pipright.drop_tip()

        print("Final mix complete.")


    def mara_distribute_multi(self, df: pd.DataFrame, variable, source_id, tip_start="A1"):
        """
        Distribute volumes from a source well into destination wells,
        batching aspirations to minimise tip changes.
        Uses 300 µL multichannel pipette in single-nozzle (partial tip) mode
        for unique per-well volumes.
        """
        vols  = df[variable].values.round(1)
        dests = df["well"].values

        if len(vols) != len(dests):
            raise ValueError("Volume list length must match number of destinations.")

        pairs = [(v, d) for v, d in zip(vols, dests) if v > 0]

        tiprack_300 = self._tipracks_by_slot["10"]

        # Partial tip pick-up: one nozzle acts as a single channel
        self.pipright.configure_nozzle_layout(
            style=SINGLE, start="A1", tip_racks=[tiprack_300]
        )
        self.pipright.starting_tip = tiprack_300.wells_by_name()[tip_start]
        self.pipright.pick_up_tip()

        idx = 0
        while idx < len(pairs):
            batch, total = [], 0
            while idx < len(pairs):
                v, _ = pairs[idx]
                if total + v <= self.pipright.max_volume:
                    batch.append(pairs[idx])
                    total += v
                    idx += 1
                else:
                    break

            self.pipright.aspirate(total, self.plate_24[source_id].bottom(1))
            self.pipright.move_to(self.plate_24[source_id].top(1))
            self.protocol.delay(seconds=2)

            for v, d in batch:
                self.pipright.dispense(
                    v,
                    self.plate_96[d].top().move(Point(x=2.0, y=0.0, z=-5))
                )

            self.pipright.blow_out(self.trash)

        self.pipright.drop_tip()

        # Restore to full 8-channel mode after partial tip use
        self.pipright.configure_nozzle_layout(style=ALL, tip_racks=[tiprack_300])

        print(f"Distribution complete: {variable} from {source_id}.")

    def final_mix_multi(self, df: pd.DataFrame, tip_start=None):
        """Mix each column — 25 cycles × 200 µL, all 8 channels simultaneously."""
        tiprack_300 = self._tipracks_by_slot["10"]

        self.pipright.configure_nozzle_layout(style=ALL, tip_racks=[tiprack_300])

        if tip_start is not None:
            self.pipright.starting_tip = tiprack_300.wells_by_name()[tip_start]

        well_names = df["well"].tolist()
        columns = sorted(set(int(w[1:]) for w in well_names))

        if len(columns) > 12:
            raise ValueError("Cannot have more than 12 columns.")

        for col in columns:
            well = self.plate_96.wells_by_name()[f"A{col}"]
            self.pipright.pick_up_tip()
            self.pipright.mix(25, 200, well.bottom(1), rate=200)
            self.pipright.drop_tip()

        print("Final mix complete.")
        






