# protocols/IMOD_quasi2D.py
from campaigns.imod_campaign import IMODCampaign
from hardware.kamome import KamomeController
from hardware.lite6 import Lite6Controller
from utils import load_conditions

CONDITIONS_URL   = "http://192.168.0.140:8000/conditions.csv"
REQUIRED_COLUMNS = ["well", "BAAc_vol", "MAI_vol", "PbI2_vol", "Anneal Time"]
SOLUTION_COLUMNS = ["BAAc_vol", "MAI_vol", "PbI2_vol"]
MIX_TIP_START   = "A1"

def run(protocol):
    robot  = IMODCampaign(protocol, "config/imod_config.yaml")
    arm    = Lite6Controller("config/lite6_config.yaml")
    kamome = KamomeController("config/kamome_config.yaml")

    df = load_conditions(CONDITIONS_URL)
    
    # Step 1 — OT-2 formulates
    robot.make_formulation(df, SOLUTION_COLUMNS, tip_start=MIX_TIP_START)
    # Step 2 — OT-2 drop-casts
    robot.drop_from_df(df)
    # Step 3 — Lite6 transfers substrates to Kamome stage
    arm.transfer_to_measurement_stage()
    # Step 4 — Kamome measures PL
    kamome.measure_pl(df["well"].tolist())


