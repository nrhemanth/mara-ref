#Imports
from opentrons import protocol_api
from opentrons.types import Location, Point

##Need to write the metadata which is the info about the protocol, who wrote it, what version was it written in etc...
metadata = {
    #'apiLevel': '2.15', ##API version 
    'protocolName': 'Checking location_Map1', #Protocol name
    'description': '''This protocol will check the location if the pipet 
                    goes to the correct location.''',
    'author': 'Clara'
    }

##Recommended to have a "Requirements" section
requirements = {"robotType": "OT-2", "apiLevel": "2.14"} ##Note: If putting 'apilevel' here, remove it from the metadata

##Defining locations - map
x = 125.3 + 10.00
y = 86.88 + 3.00
p0 = [[x + 1*x/8, y-y/3.2],
      [x + 3*x/8, y-y/3.2],
      [x + 5*x/8, y-y/3.2],
      [x + 7*x/8, y-y/3.2],
      [x + 1*x/8, y/3.2],
      [x + 3*x/8, y/3.2],
      [x + 5*x/8, y/3.2],
      [x + 7*x/8, y/3.2]]

p1 = [x+x/4,y*2-y/4]
p2 = [x*2-x/4,p1[1]]
p3 = [p1[0],y+y/4]
p4 = [p2[0],p3[1]]

def run(ctx):
    ''' input x, y, z values here (in mm). 
    Location of ice tray x = ,y = ,z = 

    '''
    #defining location of custom stuff
    loc_water = Location(Point(y*3+y/2,125/2,6),None) # location of water 
    loc0_0 = Location(Point(p0[0][0], p0[0][1], 6), None) # dispense - location of mixing
    loc0_1 = Location(Point(p0[1][0], p0[1][1], 6), None) # dispense - location of mixing
    loc1 = Location(Point(p1[0],p1[1],6),None) # location of blue dye 
    loc2 = Location(Point(p2[0],p2[1],6),None) # location of red dye 
    loc3 = Location(Point(p3[0],p3[1],6),None) # location of yellow dye
    loc4 = Location(Point(p4[0],p4[1],6),None)  # location of green dye

    #load labwear
    tiprack = ctx.load_labware('opentrons_96_tiprack_300ul', '11')
    pip = ctx.load_instrument('p300_single_gen2', 'right', tip_racks=[tiprack])

    #pick up tip
    pip.pick_up_tip(tiprack['A1']) # pick up tip
    pip.aspirate(100,loc_water)
    #protocol for just moving the tip (for checking positions)
    for i in range(len(p0)):
        #pip.move_to(Location(Point(p0[i][0], p0[i][1], 6), None))
        pip.dispense(10,Location(Point(p0[i][0], p0[i][1], 6), None))
        #pip.move_to(loc0_0)
        #pip.move_to(loc0_1)
    #pip.move_to(loc1)
    #pip.move_to(loc2)
    #pip.move_to(loc3)
    #pip.move_to(loc4)
    pip.drop_tip()