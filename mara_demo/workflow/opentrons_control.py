'''
Vattanary Tevy - created 03/02/2025
Setting up Opentrons protocol, labware, and custom functions

Running this program ...

Notes: 
'''

from opentrons import protocol_api, execute, simulate
from opentrons.types import Location, Point
from lhs import store_and_print_cmyk, generate_lhs_samples
import pandas as pd
import numpy as np
from config import OPENTRONS_API_VERSION, TIPRACK_TYPE, STOCK_PLATE_TYPE, TARGET_PLATE_TYPE, PIPETTE_TYPE, PIPETTE_MOUNT, LHS_N_SAMPLES, PLATE_ELEVATION
from config import PIPETTE_TIP_MAX_VOL, TIPRACK_SLOT, STOCK_PLATE_SLOT, STOCK_PLATE_SLOT2, TARGET_PLATE_SLOT, PLATE_OFFSET_X, PLATE_OFFSET_Y, PLATE_OFFSET_Z

def run_opentrons_mix(cmyk_input, start_well=0):
    """
    Dispenses one or multiple CMYK samples into the target plate wells.
    
    cmyk_input can be:
      - shape (4,) for a single sample, e.g. [C, M, Y, K]
      - shape (N,4) for multiple samples, e.g. [[C1, M1, Y1, K1], ..., [CN, MN, YN, KN]]
    
    We'll handle both cases by converting the single sample to a shape (1,4)
    list if needed. Then we'll loop over each row and dispense each sample 
    into a unique well of the 96-well plate.
    """

    protocol = execute.get_protocol_api(OPENTRONS_API_VERSION)
    protocol.home()

    tiprack = protocol.load_labware(TIPRACK_TYPE, TIPRACK_SLOT)
    pip = protocol.load_instrument(PIPETTE_TYPE, PIPETTE_MOUNT, tip_racks=[tiprack])
    stock_plate = protocol.load_labware(STOCK_PLATE_TYPE, STOCK_PLATE_SLOT)
    stock_plate2 = protocol.load_labware(STOCK_PLATE_TYPE, STOCK_PLATE_SLOT2)
    target_plate = protocol.load_labware(TARGET_PLATE_TYPE, TARGET_PLATE_SLOT)

    start_stock = {
    'magenta_loc': [stock_plate.wells()[0].center(), stock_plate.wells()[1].center()],
    'magenta_vol': [20000, 20000],
    'cyan_loc': [stock_plate.wells()[2].center(), stock_plate.wells()[3].center()],
    'cyan_vol': [20000, 20000],
    'yellow_loc': [stock_plate.wells()[4].center(), stock_plate.wells()[5].center()],
    'yellow_vol': [20000, 20000],
    'black_loc': [stock_plate2.wells()[0].center(), stock_plate2.wells()[1].center()],
    'black_vol': [20000, 20000]
    }
    start_stock = pd.DataFrame(data=start_stock)

    cyan_source    = start_stock["cyan_loc"][0]     # i.e. stock.wells()[2].center()
    magenta_source = start_stock["magenta_loc"][0]  # i.e. stock.wells()[0].center()
    yellow_source  = start_stock["yellow_loc"][0]   # i.e. stock.wells()[4].center()
    black_source   = start_stock["black_loc"][0]    # i.e. stock2.wells()[0].center()
    
    # Convert single sample to shape (1,4) for uniform handling

    cmyk_input = np.array(cmyk_input, dtype=float)

    if cmyk_input.ndim == 1:  
        # cmyk_input is shape (4,)
        cmyk_samples = [cmyk_input]  # shape (1,4) in list form
    else:
        # cmyk_input is shape (N,4)
        cmyk_samples = cmyk_input
    
    num_samples = len(cmyk_samples)
    for i in range(num_samples):
        c_vol, m_vol, y_vol, k_vol = cmyk_samples[i]
        
        # dispense each sample into the i-th well of the 96-well plate
        destination_well = target_plate.wells()[start_well + i]

        pip.pick_up_tip()

        # aspirate & dispense CYAN
        if c_vol > 0:
            pip.aspirate(c_vol, cyan_source)
            pip.dispense(c_vol, destination_well)

        # aspirate & dispense MAGENTA
        if m_vol > 0:
            pip.aspirate(m_vol, magenta_source)
            pip.dispense(m_vol, destination_well)

        # aspirate & dispense YELLOW
        if y_vol > 0:
            pip.aspirate(y_vol, yellow_source)
            pip.dispense(y_vol, destination_well)

        # aspirate & dispense BLACK
        if k_vol > 0:
            pip.aspirate(k_vol, black_source)
            pip.dispense(k_vol, destination_well)

        pip.blow_out(destination_well)
        pip.drop_tip()

    # end for i in range(num_samples)

    protocol.home()
    for line in protocol.commands():
        print(line)

def home_position():
    protocol = execute.get_protocol_api(OPENTRONS_API_VERSION)
    protocol.home()

def loc_stock(n_samples,fill):
    array = []
    #fill array
    for i in range(n_samples): 
        array.append(fill) 
    return array

def loc_mixing(start,n_sample): 
    array = []
    for i in range(n_sample):
        array.append(run_opentrons_mix.target_plate.wells()[i+start].top(z = PLATE_ELEVATION)) # Change elevation here using top(z=90)
#         array.append(plate.wells()[i+start].center())
    return array