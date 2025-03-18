from opentrons import protocol_api

# metadata
metadata = {
    "apiLevel": "2.19",
    "protocolName": "Serial Dilution Tutorial",
    "description": """This protocol is the outcome of following the
                   Python Protocol API Tutorial located at
                   https://docs.opentrons.com/v2/tutorial.html. It takes a
                   solution and progressively dilutes it by transferring it
                   stepwise across a plate.""",
    "author": "New API User"
    }

# requirements
requirements = {"robotType": "OT-2", "apiLevel": "2.19"}

# protocol run function
def run(protocol: protocol_api.ProtocolContext):
    # labware
    plate = protocol.load_labware(
        "corning_96_wellplate_360ul_flat", location="1"
    )
    tiprack = protocol.load_labware(
        "opentrons_96_tiprack_300ul", location="2"
    )

    # pipettes
    left_pipette = protocol.load_instrument(
        "p300_single", mount="left", tip_racks=[tiprack]
    )

    # commands
    left_pipette.pick_up_tip()
    left_pipette.aspirate(100, plate["A1"])
    left_pipette.dispense(100, plate["B2"])
    left_pipette.drop_tip()