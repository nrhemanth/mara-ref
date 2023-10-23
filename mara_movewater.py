#Imports
from opentrons import protocol_api
from opentrons.types import Location, Point

##Need to write the metadata which is the info about the protocol, who wrote it, what version was it written in etc...
metadata = {
    #'apiLevel': '2.15', ##API version 
    'protocolName': 'Checking location', #Protocol name
    'description': '''This protocol will check the location if the pipet goes to the correct location.''',
    'author': 'Clara'
    }

##Recommended to have a "Requirements" section
requirements = {"robotType": "OT-2", "apiLevel": "2.14"} ##Note: If putting 'apilevel' here, remove it from the metadata

def run(ctx):
    ''' input x, y, z values here (in mm). 
    Location of ice tray x = ,y = ,z = 

    '''
    # The coordinates are absolute 
    # with reference to the bottom left corner of slot 1 as origin.
    # x, y, and z can be a float or integer
    loc = Location(Point(150, 78, 6), None)
    loc2 = Location(Point(280,78,6),None)
    loc3 = Location(Point(330,78,6),None)
    #pipette and labware
    tiprack = ctx.load_labware('opentrons_96_tiprack_300ul', '1')
    pip = ctx.load_instrument('p300_single_gen2', 'right', tip_racks=[tiprack])
    
    #variable
    N = 10
    #commands
    pip.pick_up_tip(tiprack['C5'])
    #pip.move_to(loc)
    #pip.drop_tip()
    for i in range(N):
        pip.aspirate(200,loc)
        pip.dispense(100,loc2)
        pip.dispense(100,loc3)

