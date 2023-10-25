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
#x = 125.3 + 10.00
#y = 86.88 + 3.00

##defining location 
x5 = 118.5 + 13.3    ## x5 & y5 are the coordinates for the bottom left corner of plate 5, same idea for x2 & y2 
y5 = 79.3 + 12.3    
x2 = 118.5 + 13.3    ## x_code = x_irl + 13.3
y2 = -11 + 12.3      ## y_code = y_irl + 12.3 

## width of box measured from middle of dividers = 132.4
## height of box measured from middle of dividers = 90.3

## positions of exact center points 
p0 = [[x2 + 0.125*132.4, y2 + 0.75*90.3],
      [x2 + 0.375*132.4, y2 + 0.75*90.3],
      [x2 + 0.625*132.4, y2 + 0.75*90.3],
      [x2 + 0.875*132.4, y2 + 0.75*90.3],
      [x2 + 0.125*132.4, y2 + 0.25*90.3],
      [x2 + 0.375*132.4, y2 + 0.25*90.3],
      [x2 + 0.625*132.4, y2 + 0.25*90.3],
      [x2 + 0.875*132.4, y2 + 0.25*90.3]]

p1 = [x5+0.25*132.4, y5 + 0.75*90.3]
p2 = [x5 + 0.75*132.4,p1[1]]
p3 = [p1[0],y5 + 0.25*90.3]
p4 = [p2[0],p3[1]]



def run(ctx):
    ''' input x, y, z values here (in mm). 
    Location of ice tray x = ,y = ,z = 

    '''
    #defining location of custom stuff
    loc0_0 = Location(Point(p0[0][0], p0[0][1], 6), None) # dispense - location of mixing
    loc0_1 = Location(Point(p0[1][0], p0[1][1], 6), None) # dispense - location of mixing
    loc1 = Location(Point(p1[0],p1[1],6),None) # location of blue dye 
    loc2 = Location(Point(p2[0],p2[1],6),None) # location of red dye 
    loc3 = Location(Point(p3[0],p3[1],6),None) # location of yellow dye
    loc4 = Location(Point(p4[0],p4[1],6),None)  # location of green dye

    #load labwear
    tiprack = ctx.load_labware('opentrons_96_tiprack_300ul', '1')
    pip = ctx.load_instrument('p300_single_gen2', 'right', tip_racks=[tiprack])

    #protocol for just moving the tip (for checking positions)
    for i in range(len(p0)):
        pip.move_to(Location(Point(p0[i][0], p0[i][1], 6), None))
        #pip.delay(minutes=1)#delay
        
        
        #pip.move_to(loc0_0)
        #pip.move_to(loc0_1)

    pip.move_to(loc1)
    
    pip.move_to(loc2)
    
    pip.move_to(loc3)
    
    pip.move_to(loc4)
   
    pip.home


# def run(protocol: protocol_api.ProtocolContext): #This is the run function. The actual instruction to give to robot to do something
#     '''
#         name = protocol.load_labwear('labwear in library', location)
#         name_pipet = protocol.load_instrument('name of pipet', 'left' or 'right', tip_racks = [tips1,tips2,...])
#         transfer() #moves the liquid
#     '''
#     #Load the labwear from library
#     tips = protocol.load_labware('opentrons_96_tiprack_300ul', 1)  #96 well tip rack
#     #reservoir = protocol.load_labware('nest_12_reservoir_15ml', 6) #a reservoir
#     #plate = protocol.load_labware('nest_96_wellplate_200ul_flat', 3) #96 wellplate
#     loc = ty.Location(ty.Point(1,1,1))
#     # OT-2 protocolfor loading pipets
#     left_pipette = protocol.load_instrument('p300_single_gen2', 'left', tip_racks=[tips]) #Tip set up on the left or right. in this case, left

#     #left_pipette.transfer(100, reservoir['A1'], plate.wells())  #100ul, From --> liquid from reservoir column 1 (A1 is locaiton of liquid but reservoir only has 'A' row), destination --> 96 wellplate
