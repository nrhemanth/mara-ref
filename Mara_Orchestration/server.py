from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

# Replace with your Opentrons Robot's IP
ROBOT_IP = "192.168.0.103"
API_URL = f"http://{ROBOT_IP}:48888"

# Function to create a new OT-2 run session
def create_run():
    headers = {"Opentrons-Version": "2"}
    response = requests.post(f"{API_URL}/runs", headers=headers)
    return response.json()["data"]["id"]

# Function to send OT-2 pipetting commands
def send_protocol(run_id):
    headers = {"Opentrons-Version": "2", "Content-Type": "application/json"}
    protocol_data = {
        "data": {
            "commands": [
                {"command": "loadPipette", "params": {"pipetteName": "p300_single", "mount": "right"}},
                {"command": "loadLabware", "params": {"labwareId": "corning_96_wellplate_360ul_flat", "location": 2}},
                {"command": "aspirate", "params": {"pipette": "p300_single", "volume": 50, "location": "A1"}},
                {"command": "dispense", "params": {"pipette": "p300_single", "volume": 50, "location": "B2"}},
                {"command": "dropTip", "params": {"pipette": "p300_single"}}
            ]
        }
    }
    response = requests.post(f"{API_URL}/runs/{run_id}/commands", headers=headers, json=protocol_data)
    return response.json()

# Function to start execution
def start_execution(run_id):
    start_data = {"data": {"actionType": "play"}}
    headers = {"Opentrons-Version": "2"}
    response = requests.post(f"{API_URL}/runs/{run_id}/actions", headers=headers, json=start_data)
    return response.json()

# Flask route to trigger the OT-2 robot
@app.route('/run_ot2', methods=['POST'])
def run_ot2():
    try:
        run_id = create_run()  # Step 1: Create a new run session
        protocol_response = send_protocol(run_id)  # Step 2: Send pipetting protocol
        execution_response = start_execution(run_id)  # Step 3: Start execution
        return jsonify({
            "run_id": run_id,
            "protocol_response": protocol_response,
            "execution_response": execution_response
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Flask route to check OT-2 API status
@app.route('/robot_status', methods=['GET'])
def check_status():
    response = requests.get(f"{API_URL}/health")
    return jsonify(response.json())

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000)
