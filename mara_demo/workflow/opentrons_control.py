'''
Vattanary Tevy - created 03/02/2025
Setting up Opentrons protocol, labware, and custom functions, plus a WebSocket server
to wait for messages from an external device
'''

import pandas as pd
import numpy as np

from opentrons import protocol_api, execute
from lhs import store_and_print_cmyk, generate_lhs_samples
from config import (
    OPENTRONS_API_VERSION, TIPRACK_TYPE, STOCK_PLATE_TYPE, TARGET_PLATE_TYPE,
    PIPETTE_TYPE, PIPETTE_MOUNT, LHS_N_SAMPLES, PLATE_ELEVATION,
    PIPETTE_TIP_MAX_VOL, TIPRACK_SLOT, STOCK_PLATE_SLOT, STOCK_PLATE_SLOT2,
    TARGET_PLATE_SLOT, PLATE_OFFSET_X, PLATE_OFFSET_Y, PLATE_OFFSET_Z
)

# -------------------- WEBSOCKET IMPORTS --------------------
import websockets
import asyncio
import json

def run_opentrons_mix(cmyk_input, start_well=0):
    """
    Dispenses one or multiple CMYK samples into the target plate wells.
    cmyk_input can be shape (4,) or shape (N,4).
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

    cyan_source    = start_stock["cyan_loc"][0]
    magenta_source = start_stock["magenta_loc"][0]
    yellow_source  = start_stock["yellow_loc"][0]
    black_source   = start_stock["black_loc"][0]
    
    # Convert single sample to shape (1,4) if needed
    cmyk_array = np.array(cmyk_input, dtype=float)
    if cmyk_array.ndim == 1:
        cmyk_array = np.expand_dims(cmyk_array, axis=0)  # shape (1,4)

    num_samples = cmyk_array.shape[0]

    # cmyk_array: shape (N,4)
    # We'll break it into columns: 
    #   c_col = cmyk_array[:,0], m_col=cmyk_array[:,1], y_col=cmyk_array[:,2], k_col=cmyk_array[:,3]
    c_col = cmyk_array[:,0]
    m_col = cmyk_array[:,1]
    y_col = cmyk_array[:,2]
    k_col = cmyk_array[:,3]

    # Dispense all C at once
    pip.pick_up_tip()
    for i in range(num_samples):
        c_vol = c_col[i]
        if c_vol > 0:
            pip.aspirate(c_vol, cyan_source.center())
            pip.dispense(c_vol, target_plate.wells()[start_well + i])
    pip.blow_out()
    pip.drop_tip()

    # Dispense all M
    pip.pick_up_tip()
    for i in range(num_samples):
        m_vol = m_col[i]
        if m_vol > 0:
            pip.aspirate(m_vol, magenta_source.center())
            pip.dispense(m_vol, target_plate.wells()[start_well + i])
    pip.blow_out()
    pip.drop_tip()

    # Dispense all Y
    pip.pick_up_tip()
    for i in range(num_samples):
        y_vol = y_col[i]
        if y_vol > 0:
            pip.aspirate(y_vol, yellow_source.center())
            pip.dispense(y_vol, target_plate.wells()[start_well + i])
    pip.blow_out()
    pip.drop_tip()

    # Dispense all K
    pip.pick_up_tip()
    for i in range(num_samples):
        k_vol = k_col[i]
        if k_vol > 0:
            pip.aspirate(k_vol, black_source.center())
            pip.dispense(k_vol, target_plate.wells()[start_well + i])
    pip.blow_out()
    pip.drop_tip()

    protocol.home()

    # Print Opentrons commands
    for line in protocol.commands():
        print(line)

def home_position():
    protocol = execute.get_protocol_api(OPENTRONS_API_VERSION)
    protocol.home()

# -------------------- WEBSOCKET SERVER CODE --------------------
async def handle_connection(websocket, path):
    """
    This function is called whenever a client (e.g. external laptop) connects.
    We read JSON messages in a loop. Each message is expected to have:
        {
            "command": "dispense" or "home" etc.,
            "cmyk": [C, M, Y, K],
            "start_well": int
        }
    We'll parse that and call the appropriate function, then send back a response.
    """
    async for message in websocket:
        try:
            data = json.loads(message)
            cmd = data.get("command", "").lower()
            
            if cmd == "dispense":
                cmyk = data["cmyk"]  # e.g. [10, 20, 30, 40]
                start_well = data.get("start_well", 0)
                run_opentrons_mix(cmyk, start_well)
                response = {"status": "ok", "message": "Dispense completed"}
                await websocket.send(json.dumps(response))

            elif cmd == "home":
                home_position()
                response = {"status": "ok", "message": "Robot homed"}
                await websocket.send(json.dumps(response))

            else:
                response = {"status": "error", "message": "Unknown command"}
                await websocket.send(json.dumps(response))

        except Exception as e:
            print(f"Exception while handling message: {e}")
            response = {"status": "error", "message": str(e)}
            await websocket.send(json.dumps(response))


async def main_server(host="0.0.0.1", port=9876):
    """
    Starts the websocket server that listens for commands.
    For example: ws://<ROBOT_IP>:8765
    """
    print(f"Starting WebSocket server on {host}:{port}")
    async with websockets.serve(handle_connection, host, port):
        print("Opentrons server is listening...")
        await asyncio.Future()  # Keep running forever

if __name__ == "__main__":
    # If we run this script directly, it starts the WebSocket server
    # so the robot is always waiting for external commands.
    asyncio.run(main_server())