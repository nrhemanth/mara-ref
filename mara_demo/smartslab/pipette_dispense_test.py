from opentrons import protocol_api, simulate

metadata = {
    'protocolName': 'pipette_dispense_test',
    'description': '''Dispense a desired volume of DI water on a scale for accuracy measurements''',
    'author': 'Tommy Zhang'
}
prot = simulate
requirements = {"robotType": "OT-2", "apiLevel": "2.16"}

""" Parameters """
aspirate_rate = 1.0 # multiplier from default
dispense_rate = 1.0 # multiplier from default
volume = 50 # microliters
pipette_max_volume = 300

def run(protocol: protocol_api.ProtocolContext):
    tips = protocol.load_labware('opentrons_96_tiprack_300ul', 1)
    reservoir = protocol.load_labware("nest_12_reservoir_15ml", 2)
    plate = protocol.load_labware("nest_96_wellplate_200ul_flat", 3)
    pip = protocol.load_instrument("p300_single_gen2", "right", tip_racks=[tips])

    pip.pick_up_tip()
    for i in range(int(pipette_max_volume / volume)):
        pip.well_bottom_clearance.aspirate = 12 # offset 12mm for the scale
        pip.aspirate(volume, reservoir["A1"], rate=aspirate_rate)
        # Location D6 near middle of well plate (put scale there)
        pip.dispense(volume, plate["D6"], rate=dispense_rate)

    pip.drop_tip(tips["A1"])



    # go to reservoir and aspirate
    # go to scale and dispense (certain volume multiple times)
    # go to reservoir, blowout, aspirate again
    # repeat
    # maybe add delay