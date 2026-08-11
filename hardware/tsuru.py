"""
Chracterization system
Replace Kamome gantry with Tsuru gantry for multi-mode characterization

PL, UV-Vis,Thermal imaging, regular camera

Current mode: PL and regular camera
"""

import os
import sys


from Tsuru import Tsuru_sdk,TsuruConnection, PLATE_TYPES
