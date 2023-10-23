## Imports
from opentrons import protocol_api
from opentrons.types import Location, Point

## Need to write the metadata which is the info about the protocol, who wrote it, what version was it written in etc...
metadata = {
    #'apiLevel': '2.15', ##API version 
    'protocolName': 'Mixing colors', #Protocol name
    'description': '''This protocol is the outcome of following the
                   Python Protocol API, reference:
                   https://support.opentrons.com/s/article/Understanding-the-X-Y-Z-coordinates-of-the-OT-2 It takes a
                   transfer water to two lotation.''',
    'author': 'Clara'
    }

## Recommended to have a "Requirements" section
requirements = {"robotType": "OT-2", "apiLevel": "2.14"} ##Note: If putting 'apilevel' here, remove it from the metadata

##Defining locations - map
x = 125.3 + 10.00
y = 86.88 + 7.00
p0 = [x*2+x/2,y+y/2]
p1 = [x+x/4,y*2-y/4]
p2 = [x*2-x/4,p1[1]]
p3 = [p1[0],y+y/4]

def run(ctx):
    ''' input x, y, z values here (in mm). 
    Location of ice tray x = ,y = ,z = 
    '''
    ## The coordinates are absolute 
    ## with reference to the bottom left corner of slot 1 as origin.
    ## x, y, and z can be a float or integer
    loc0 = Location(Point(p0[0], p0[1], 6), None) # dispense - location of mixing
    loc1 = Location(Point(p1[0],p1[1],6),None) # location of blue dye 
    loc2 = Location(Point(p2[0],p2[1],6),None) # location of red dye 
    loc3 = Location(Point(p3[0],p3[1],6),None) # location of yellow dye

    ## pipette and labware
    tiprack = ctx.load_labware('opentrons_96_tiprack_300ul', '4')
    pip = ctx.load_instrument('p300_single_gen2', 'right', tip_racks=[tiprack])

    ## change amount
    nb = [100,100,50]
    nr = [100,100,50]
    ny = [20]
    ## commands
    pip.pick_up_tip(tiprack['A1']) # pick up tip
    for i in range (len(nb)):
        pip.aspirate(nb[i],loc1) # pick up blue 
        pip.dispense(nb[i],loc0)# dispense blue
    pip.drop_tip() # drop blue tip

    pip.pick_up_tip(tiprack) # pick up tip
    for i in range(len(nr)):
        pip.aspirate(nr[i],loc2) # pick up red 
        pip.dispense(nr[i],loc0)# dispense red
    pip.drop_tip() # drop red tip

    pip.pick_up_tip(tiprack) # pick up tip
    for i in range(len(ny)):
        pip.aspirate(ny[i],loc3) # pick up yellow
        pip.dispense(ny[i],loc0)# dispense yellow

    pip.mix(10, 100, loc0)

    pip.drop_tip() # drop red tip

    # for i in range(N):
    #     pip.dispense(100,loc3)

## NOTES for other commands
#pip.move_to(loc)
##mix - aspirate and dispense multiple times
#pipette.mix(4, 100, plate.wells('A2'))   # mix 4 times, 100uL, in plate:A2
#pipette.mix(3, 50)                       # mix 3 times, 50uL, in current location
#pipette.mix(2)                           # mix 2 times, pipette's max volume, in current location
