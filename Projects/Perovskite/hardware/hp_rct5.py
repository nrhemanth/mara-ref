#hp rct5 (Hot plate, IKA RCT5)


def set_opentron_heater(self, slot):
        # Load heater
        self.hs_mod = self.protocol.load_module("heaterShakerModuleV1", slot)
        self.hs_adapter = self.hs_mod.load_adapter("opentrons_universal_flat_adapter")
        self.hs_plate = self.hs_adapter.load_labware("corning_384_wellplate_112ul_flat")

        # heater offsets for dropcasting on to rectangle 12 samples
        self.hs_wells = {
            1: ('C4',  (-0.5, 1, 0)),
            2: ('C10', (-1.5, 1, 0)),
            3: ('C16', (-2.5, 1, 0)),
            4: ('C21', (1, 1, 0)),
            5: ('H4',  (0, -3, 0)),
            6: ('H10', (-1.5, -3, 0)),
            7: ('H16', (-2.5, -3, 0)),
            8: ('H21', (1.5, -3, 0)),
            9: ('N4',  (0, -1, 0)),
            10: ('N10', (-1, -1, 0)),
            11: ('N16', (-2.5, -1, 0)),
            12: ('N21', (1.5, -1, 0))
        }
        return self.hs_mod, self.hs_plate, self.hs_wells
    
def set_custom_heater(self, slot):
    # heater offsets for dropcasting on to rectangle 12 samples
    # diameter o f96 = 7.0mm
    heater_plate = self.protocol.load_labware('opentrons_96_wellplate_200ul_pcr_full_skirt', slot)
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

def start_heater(self):
    '''
    heater_mod: heater module from labware
    heater_plate: heater plate from labware
    '''
    # Close the opentron flap and start heater
    self.hs_mod.close_labware_latch()
    self.hs_mod.set_and_wait_for_temperature(95)
    print("✅ Heater Started")
    # self.print_cmd()

def stop_heater(self):
    '''
    Turns off the heater and opens the latch
    '''
    self.hs_mod.deactivate_heater()
    self.hs_mod.open_labware_latch()
    print("🛑 Heater Stopped")
    # self.print_cmd()