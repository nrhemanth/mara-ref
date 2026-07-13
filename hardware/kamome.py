from kamome_sdk import Kamome

PORT = "COM3"  # Windows — use "/dev/ttyUSB0" on Linux/Mac

gantry = Kamome(PORT)

gantry.check_connection()

# 2. Scan a sub-region
gantry.scan("Corning_96", wait_ms=1500, start_well="A4", end_well="D7")
