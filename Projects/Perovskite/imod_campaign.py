# modules/campaign.py
from modules.ot2.formulations import Formulations
from modules.ot2.drop_casting import DropCasting
from src.mara.utils import add_material
import pandas as pd


class IMODCampaign(Formulations, DropCasting):
    """
    Combines formulation and drop casting for the IMOD protocol.
    No new methods needed — this just joins the two sibling classes.
    Python's MRO handles the method resolution automatically.
    """

    SOLUTION_COLUMNS = ["BAAc_vol", "MAI_vol", "PbI2_vol"]

    def make_formulation(self, df: pd.DataFrame, columns: list, tip_start="A1"):
        """IMOD-specific formulation — knows which columns to use."""
        """
        Full sequence: distribute all solutions then final mix.
        source_wells order matches columns order (set in config under labware.source_wells).
        """
        source_wells = self.labware.get("source_wells", ["A1", "B1", "C1"])

        for source_well, column in zip(source_wells, columns):
            self.mara_distribute(df, column, source_well, tip_start)
            self.clear_commands()

        self.final_mix(df)

    def drop_from_df(self, df: pd.DataFrame):
        """IMOD-specific drop casting — uses the 'well' column for source wells."""
        self.dropcasting(df)
    


    

