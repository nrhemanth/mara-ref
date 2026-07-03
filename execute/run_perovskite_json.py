from src.mara.runtime import CapyClient, TERMINAL_STATUSES                       
from pathlib import Path
import os, sys

with CapyClient(os.environ['ROBOT_URL']) as c:
    p = c.upload_protocol_with_files(
        Path('modules/mara_perovskite.py'),
        Path('custom_labware/single_bundle_6_channel.json'),
    )
    print('uploaded:', p.id)

    p = c.wait_for_analysis(p.id)
    status = p.analysisSummaries[0]['status']
    print('analysis:', status)
    if status != 'completed':
        print('errors:', p.analysisSummaries[0].get('errors'))
        sys.exit(1)

    run = c.create_run(p.id)
    print('run id:', run.id)

    c.run_action(run.id, 'play')
    print('started — do not move the robot!')

    for snap in c.stream_status(run.id):
        print(' ', snap.status)

    print('done:', snap.status)
