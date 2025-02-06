from opentrons import protocol_api, simulate, robot
import time

metadata = {
    'protocolName': 'checkerboard_test',
    'description': '''Dispense checkerboard pattern of two solutions for cross-contamination testing''',
    'author': 'Tommy Zhang'
}
prot = simulate
requirements = {"robotType": "OT-2", "apiLevel": "2.16"}

""" Parameters """
aspirate_rate = 1.0 # multiplier from default max 3x
dispense_rate = 1.0 # multiplier from default max 3x
blowout = False # blowout boolean
touchtip = False # touchtip boolean

# carriage movement speed default 400mm/s (not recommended to increase)

"""
Tips located in location 1
Reservoir (6 well plate) located in location 2
96 well plate located in location 3
Using 300uL pipette tips and p300_single_gen2 
"""
def run(protocol: protocol_api.ProtocolContext):
    tips = protocol.load_labware('opentrons_96_tiprack_300ul', 1)
    reservoir = protocol.load_labware("corning_6_wellplate_16.8ml_flat", 2)
    plate = protocol.load_labware("corning_96_wellplate_360ul_flat", 3)
    pip = protocol.load_instrument("p300_single_gen2", "right", tip_racks=[tips])

    well_a = []  # list of all well locations for solution one
    well_b = []  # list of all well locations for solution two
    for i in range(96):
        if i % 2 == 0:
            well_a.append(plate.wells()[i])
        else:
            well_b.append(plate.wells()[i])

    # 1) go to reservoir, and aspirate 300uL
    # 2) go to next 3 wells in sequence and dispense in wells
    # 3) go to reservoir, dispense/blowout
    # repeat 1-3 until 96 well plate is filled

    def fill_wells(well_list, reservoir_loc):
        pip.pick_up_tip() # pick up a new tip
        pip.aspirate(300, reservoir[reservoir_loc], rate=aspirate_rate) # aspirate first soln
        for i in range(len(well_a)): # loop through each position in half of checkerboard
            st = time.time()
            if i % 3 == 0 and i != 0: # every three dispenses we run out of solution
                pip.dispense(15, reservoir[reservoir_loc], rate=dispense_rate) # dispense rest of soln
                pip.blow_out() # ensure all soln leaves pipette tip using blowout function
                pip.aspirate(300, reservoir[reservoir_loc], rate=aspirate_rate) # aspirate more soln
            pip.dispense(95, well_list[i], rate=dispense_rate) # dispense into ith well
            if touchtip:  # if touchtip parameter true, then perform touch tip in well
                pip.touch_tip()
            et = time.time()
            #protocol.comment(f'Fill 3 well time: {et-st}')

    a_st = time.time()
    fill_wells(well_a, "A1")
    pip.drop_tip(tips["A1"])
    a_et = time.time()

    b_st = time.time()
    fill_wells(well_b, "B1")
    pip.drop_tip(tips["B1"])
    b_et = time.time()

    protocol.home()
    protocol.comment(f'A_well total time: {a_et-a_st}s, B_well total time: {b_et-b_st}s')