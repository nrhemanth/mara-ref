'''
Vattanary Tevy - created 03/02/2025
Connects to Arducam via Websockets

Running this program connects to the given camera WebSocket, capture a photo, 
save it to disk, and return the saved file path
'''

import base64
import websockets
import asyncio
from config import CAPTURE_IMAGE_PATH, CAMERA_URI
from IPython.display import display, Image as IPythonImage

async def capture_photo():
    async with websockets.connect(CAMERA_URI, max_size=5_000_000) as ws:
        
        # send command to capture a picture
        await ws.send("capture")
        # wait for response
        response = await ws.recv()
        # decode from Base64
        img_data = base64.b64decode(response)

        display(IPythonImage(data=img_data), format='jpg')
        print("Image captured")

        with open(CAPTURE_IMAGE_PATH, "wb") as f:
            f.write(img_data)
        print(f"Image saved at: {CAPTURE_IMAGE_PATH}")
        
    return CAPTURE_IMAGE_PATH

# if __name__ == "__main__":
#     result = asyncio.run(capture_photo())
#     print(result)