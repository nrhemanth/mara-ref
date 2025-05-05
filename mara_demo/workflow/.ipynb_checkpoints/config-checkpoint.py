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

LHS_N_SAMPLES = 4
LHS_N_VARS = 4  # CMYK

# LHS
LHS_SEEDS = 1
LHS_OUTPUT_JSON = "CMYK_values.json"

# BO
TARGET_RGB = [75, 46, 131]

BO_MAX_ITERS = 20
ACQUISITION_EI = 0.01
BO_SEED = 1

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
STOCK_PLATE_SLOT = "3"
STOCK_PLATE_SLOT2 = "2"
TARGET_PLATE_SLOT = "1"

PLATE_OFFSET_X = 0
PLATE_OFFSET_Y = 0
PLATE_OFFSET_Z = 33