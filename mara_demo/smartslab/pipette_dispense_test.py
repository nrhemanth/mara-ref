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
# flow rate
# etc...

def run(protocol: protocol_api.ProtocolContext):
    tips = protocol.load_labware('opentrons_96_tiprack_300ul', 1)
    reservoir = protocol.load_labware("nest_12_reservoir_15ml", 2)
    plate = protocol.load_labware("nest_96_wellplate_200ul_flat", 3)
    pip = protocol.load_instrument("p300_single_gen2", "right", tip_racks=[tips])


    # go to reservoir and aspirate
    # go to scale and dispense (certain volume multiple times)
    # go to reservoir, blowout, aspirate again
    # repeat
    # maybe add delay