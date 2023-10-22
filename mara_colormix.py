#Imports
from opentrons import protocol_api
from opentrons.types import Location, Point

##Need to write the metadata which is the info about the protocol, who wrote it, what version was it written in etc...
metadata = {
    #'apiLevel': '2.15', ##API version 
    'protocolName': 'Moving Water', #Protocol name
    'description': '''This protocol is the outcome of following the
                   Python Protocol API, reference:
                   https://support.opentrons.com/s/article/Understanding-the-X-Y-Z-coordinates-of-the-OT-2 It takes a
                   transfer water to two lotation.''',
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
    loc0 = Location(Point(150, 78, 6), None)
    loc1 = Location(Point(28,78,6),None)
    loc2 = Location(Point(280,78,6),None)
    loc3 = Location(Point(330,78,6),None)


    #pipette and labware
    tiprack = ctx.load_labware('opentrons_96_tiprack_300ul', '1')
    pip = ctx.load_instrument('p300_single_gen2', 'right', tip_racks=[tiprack])
    
    #commands
    pip.pick_up_tip(tiprack['A1']) # pick up tip
    pip.aspirate(200,loc) # pick up blue 
    pip.dispense(100,loc2)# dispense blue
    pip.drop_tip() # drop blue tip

    pip.pick_up_tip(tiprack) # pick up tip
    pip.aspirate(200,loc) # pick up red 
    pip.dispense(100,loc2)# dispense red
    pip.drop_tip() # drop red tip

    pip.pick_up_tip(tiprack) # pick up tip
    pip.aspirate(200,loc) # pick up yellow
    pip.dispense(100,loc2)# dispense yellow
    pip.drop_tip() # drop yellow tip


    # for i in range(N):
    #     pip.dispense(100,loc3)

## NOTES for other commands
#pip.move_to(loc)