"""End-to-end demo: upload examples/home.py, preflight, run, stream status.

Usage (against the mock):
    mara-mock-robot &
    python -m examples.preflight_home

Against mara:
    ROBOT_URL=http://capy.local:31950 python -m preruns.preflight_home
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from mara.preflight import confirm_deck_state
from mara.runtime import CapyClient, TERMINAL_STATUSES

HERE = Path(__file__).resolve().parent

def main(protocol_file: Path, csv_file: Path | None)->int:
# def main(protocol_file: Path) -> int:
    url = os.environ.get("ROBOT_URL", "http://192.168.1.101:31950")    
    with CapyClient(url) as capy:
        capy.health()
        protocol = capy.upload_protocol(protocol_file)
        print(f"uploaded {protocol.id}")

        if not confirm_deck_state(capy, image_path=HERE / "preflight.jpg"):
            print("preflight not confirmed; aborting", file=sys.stderr)
            return 1

        run = capy.create_run(protocol.id)
        capy.run_action(run.id, "play")
        for snap in capy.stream_status(run.id, poll_interval=0.5):
            print(f"  status: {snap.status}")
            if snap.status in TERMINAL_STATUSES:
                break
        print(f"final: {snap.status}")
        return 0 if snap.status == "succeeded" else 2


# if __name__ == "__main__":
#     protocol_file = sys.argv[1]
#     if not Path(protocol_file).is_file():
#         raise SystemExit(f"File {protocol_file} not found")
#     sys.exit(main(Path(protocol_file)))

if __name__ == "__main__":
    protocol_file = Path(sys.argv[1])

    csv_file = Path(sys.argv[2]) if len(sys.argv) > 2 else None

    if not Path(protocol_file).is_file():
        raise SystemExit(f"File {protocol_file} not found")

    sys.exit(main(protocol_file, csv_file))
