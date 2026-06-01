import pandas as pd
from opentrons.types import Point
from src.mara.utils import add_material
from Projects.Perovskite.hardware.ot2 import OT2Controller


class DropCasting(OT2Controller):
    def __init__(self, protocol, config_path=None):
        super().__init__(protocol, config_path)

    def dropcasting(self, df: pd.DataFrame):
            '''
            Perform dropcasting from 96-well to 384-well with manual tip tracking.
            mix_well: array of stock locations
            hs_well: array of well locations
            volume: integer volume, Recommended 2 µL
            '''
            aspirate_volume = 5
            drop_volume = 1.5
            anneal_time = df['Anneal Time'].tolist()
            sample_wells = df['well'].tolist()
            

            if len(df) > len(self.hs_wells):
                raise ValueError(f":x: Too many samples ({len(df)}). Only {len(self.hs_wells)} destination wells are supported.")

            for i, (src, time) in enumerate(zip(sample_wells, anneal_time), start=1):
                if i not in self.hs_wells:
                    raise ValueError(f"Missing HS well mapping for sample index {i}.")

                dest_well, offset = self.hs_wells[i]

                self.pip20.pick_up_tip()

                # Aspirate from 96-well plate
                self.pip20.aspirate(aspirate_volume, self.plate_96.wells_by_name()[src].bottom(1))

                # Dispense into 384-well with specified offset
                self.pip20.dispense(
                    drop_volume,
                    self.hs_plate.wells_by_name()[dest_well].bottom(0.05).move(Point(*offset))
                )

                self.protocol.delay(seconds=1)

                self.pip20.drop_tip()

                # Log or trigger anneal time
                
                add_material(f"Sample: {dest_well}", time)

    def dropcast_selected(self, source, destination, drop_volume=3):
        '''
        Perform dropcasting for selected wells from 96-well to 384-well.
        source: list of well names from the 96-well plate
        destination: list of integer keys for the heater shaker wells (1-12)

        volume: integer volume, Recommended 2 µL
        '''

        # Source wells (from mixture)
        selected_rows = df[df['well'].isin(source)].copy()
        selected_rows = pd.concat([selected_rows[selected_rows['well'] == s].iloc[[0]] for s in source], ignore_index=True)
        anneal_time = selected_rows['Anneal Time'].tolist()
        sample_wells = selected_rows['well'].tolist()
        # Destination plate (on heater)
        destinations = [self.hs_wells[d] for d in destination]
        # Volume to drop cast
        drop_volume = drop_volume
        aspirate_volume = drop_volume*2

        if len(selected_rows) > len(destinations):
            raise ValueError(f":x: Too many samples ({len(df)}). Only {len(destinations)} destination wells are supported.")
        
        # drop casting
        for src, dest_idx, time in zip(sample_wells, destination, anneal_time):
            well_name, offset = self.hs_wells[dest_idx]
            self.pip20.pick_up_tip()
            self.pip20.aspirate(aspirate_volume , self.plate_96.wells_by_name()[src].bottom(1))
            self.pip20.dispense(drop_volume, self.hs_plate.wells_by_name()[well_name].bottom(0.05).move(Point(*offset)))
            # self.pip20.blow_out(self.hs_plate.wells_by_name()[well_name].bottom(0.5).move(Point(*offset)))
            self.protocol.delay(seconds=1)
            self.pip20.drop_tip()
            add_material(f"Sample: {well_name}", time)

        # print(":white_check_mark: Complete Dropcasting")
        # self.print_cmd()

    def dropcast_manual(self, source, destination, drop_volume=3):
            '''
            Perform dropcasting from 96-well to 384-well with manual tip tracking.
            mix_well: array of stock locations
            hs_well: array of well locations
            volume: integer volume, Recommended 2 µL
            '''

            # Source wells (from mixture)
            sample_wells = source
            # Destination plate (on heater)
            destinations = destination # [self.hs_wells[d] for d in destination]
            # Volume to drop cast
            drop_volume = drop_volume
            aspirate_volume = drop_volume + 3

            # drop casting
            for src, dest_idx in zip(sample_wells, destinations):
                well_name, offset = self.hs_wells[dest_idx]
                self.pip20.pick_up_tip()
                self.pip20.aspirate(aspirate_volume, self.plate_96.wells_by_name()[src].bottom(1))
                self.pip20.dispense(drop_volume, self.hs_plate.wells_by_name()[well_name].bottom(0.01).move(Point(*offset)))
                #self.pip20.blow_out(self.hs_plate.wells_by_name()[well_name].bottom(0.5).move(Point(*offset)))
                self.protocol.delay(seconds=1)
                self.pip20.drop_tip()
