# WebSocket-Based Image Capture System - Raspberry Pi, connecting to Arducam, websockets, ssh
This project enables real-time image capture using a Raspberry Pi camera and WebSockets. It facilitates low-latency communication between a Python WebSocket server (running on the Raspberry Pi) and a client (running in Jupyter Notebook). The captured image is displayed in Jupyter Notebook and saved locally.

## Why Use WebSockets?
- **Low Latency:** Ideal for image capture and task processing.
- **Supports Multiple Clients:** Maintains an open communication channel.
- **More Efficient than HTTP:** Uses a single open connection instead of creating new ones for each request/response.

### When to Use Flask Instead:
- If the implementation needs to be simple and highly compatible with Jupyter.
- If image capture requests are infrequent (HTTP requests are independent).

## Installation & Setup

### 1. Install Dependencies
Ensure you have Python installed. Then install the required packages:

```sh
pip install websockets opencv-python numpy matplotlib pillow
```

### 2. Setup the WebSocket Server on Raspberry Pi
Run the following script (server.py) on the Raspberry Pi to start the WebSocket server:

```sh
python3 Documents/server.py
```
This server:
- Captures an image when requested.
- Sends the captured image as a byte stream to the client.

### 3. Run the WebSocket Client
On the client machine (e.g., Jupyter Notebook), run the main.py (for full workflow) or Arducam_Integration.ipynb (for single image capturing) script to request an image capture.

### 4. Expected Output
- The captured image is displayed in Jupyter Notebook.
- The image is saved locally as 'captured_image.png'.

## How It Works
WebSocket Server (server.py):
- Starts a WebSocket server on 0.0.0.0:8765 (listens for connections from any client).
- Waits for client messages:
    - If it receives "capture", it:
        1. Runs libcamera-jpeg to capture an image and save it as test.jpg.
        2. Reads the image file and encodes it in base64.
        3. Sends the base64-encoded image to the client.
    - If an unknown command is received, it responds with an error message.
- Handles client connections gracefully (detects disconnections).

WebSocket Client:
- Connects to Raspberry Pi.
- Sends "capture" command and waits for a response.
- Receives Base64 image, decodes it, and displays it.

## Connecting to Raspberry Pi through ssh (Optional)
Remotely access Raspberry Pi's terminal

### 1. Find Raspberry Pi's IP address using:

```sh
hostname -I
```

### 2. On your device, in terminal, run:

(in Mara's case)
```sh
ssh mara@172.28.236.86
```

### 3. Enter password

For Mara's Raspberry Pi, the password is 'mara'.

## Troubleshooting
1. WebSocket Connection Issues
- Ensure the server is running on the Raspberry Pi.
- Verify the correct IP address (hostname -I).
- Check firewall settings (sudo ufw allow 8765/tcp).

2. Image Capture Issues
- Ensure libcamera-jpeg is installed on Raspberry Pi:

```sh
sudo apt install libcamera-apps
```

- Verify camera permissions (sudo chmod 777 /dev/video0).
- Test camera manually:

```sh
libcamera-jpeg -n -t 1 -o test.jpg
```

# Orchestration

