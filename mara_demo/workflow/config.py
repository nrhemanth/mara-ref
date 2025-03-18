'''
Vattanary Tevy - created 03/02/2025
Global parameters and references 
'''

from pathlib import Path

IMAGE_DIR = Path.cwd() / "images"
IMAGE_DIR.mkdir(exist_ok=True)

# camera parameters
CAMERA_URI = "ws://172.28.236.86:8765"
CAPTURE_IMAGE_PATH = str(IMAGE_DIR / "captured.jpg")

# standard row/col sizes and well volume
ROWS = 8
COLS = 12
TOP_LEFT = (265, 278)
BOTTOM_RIGHT = (2989, 2006)
MAX_WELL_VOLUME = 270

# LHS
LHS_SEEDS = [1]
LHS_OUTPUT_JSON = "CMYK_values.json"
LHS_N_SAMPLES = 4
LHS_N_VARS = 4  # CMYK

# BO
# TARGET_RGB = [75, 46, 131]
# dark purple (more appropriate purple for camera)
# TARGET_RGB = [62, 52, 50]
# lighter purple (for white cap/background)
TARGET_RGB = [96, 86, 87]

BO_MAX_ITERS = 15
INITIAL_SAMPLE = 5
ACQUISITION_EI = 0.01
BO_SEED = [1]

# kernel parameters
RBF_LENGTH_SCALE = 1.0
CONSTANT_VALUE = 1.0

# opentrons
OPENTRONS_API_VERSION = '2.19'
TIPRACK_TYPE = "opentrons_96_tiprack_300ul"
STOCK_PLATE_TYPE = "corning_6_wellplate_16.8ml_flat"
TARGET_PLATE_TYPE = "opentrons_96_wellplate_200ul_pcr_full_skirt"

PIPETTE_TYPE = "p300_single_gen2"
PIPETTE_MOUNT = "right"
PIPETTE_TIP_MAX_VOL = 300

TIPRACK_SLOT = "6"
STOCK_PLATE_SLOT = "5"
STOCK_PLATE_SLOT2 = "8"
TARGET_PLATE_SLOT = "1"

PLATE_OFFSET_X = 0
PLATE_OFFSET_Y = 0
PLATE_OFFSET_Z = 33

PLATE_ELEVATION = 85