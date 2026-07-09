# Mara_Opentron
Code related to the OpenTron OT-2 Robot.



# How to use the visualize simulate:
## Default: saves <protocol>_simulation.png alongside the protocol
python runs/visualize_simulate.py modules/mara_mof_singlefile.py

## Custom output path
python runs/visualize_simulate.py modules/mara_mof_singlefile.py --out results/run1.png


## Test

python -c "
from src.mara.runtime import CapyClient
from pathlib import Path
import os

with CapyClient(os.environ['ROBOT_URL']) as c:
    p = c.upload_protocol_with_files(
        Path('modules/mara_perovskite.py'),
        Path('custom_labware/single_bundle_6_channel.json'),
    )
    print('uploaded:', p.id)
    p = c.wait_for_analysis(p.id)
    status = p.analysisSummaries[0]['status']
    print('analysis:', status)
"


## Run it 
python -c "
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
"

Error message: 
Traceback (most recent call last):
  File "<string>", line 20, in <module>
  File "C:\Users\cnt25\Documents\GitHub\Mara\src\mara\runtime.py", line 250, in create_run
    r = self._request("POST", "/runs", json=body)
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\cnt25\Documents\GitHub\Mara\src\mara\runtime.py", line 166, in _request
    raise CapyError(r)
src.mara.runtime.CapyError: POST http://192.168.1.102:31950/runs -> 500: {'errors': [{'id': 'UnexpectedError', 'title': 'Unexpected Internal Error', 'detail': 'ExceptionGroup: unhandled errors in a TaskGroup (1 sub-exception)', 'meta': {'type': 'ExceptionGroup', 'code': '4000', 'message': 'ExceptionGroup: unhandled errors in a TaskGroup (1 sub-exception)', 'detail': {'args': '(\'unhandled errors in a TaskGroup\', [NameError("name \'__file__\' is not defined")])', 'exceptions': '(NameError("name \'__file__\' is not defined"),)', 'message': 'unhandled errors in a TaskGroup', 'traceback': '  File "/usr/lib/python3.12/site-packages/starlette/middleware/errors.py", line 162, in __call__\n    await self.app(scope, receive, _send)\n\n  File "/usr/lib/python3.12/site-packages/starlette/middleware/base.py", line 106, in __call__\n    async with anyio.create_task_group() as task_group:\n               ^^^^^^^^^^^^^^^^^^^^^^^^^\n\n  File "/usr/lib/python3.12/site-packages/anyio/_backends/_asyncio.py", line 772, in __aexit__\n    raise BaseExceptionGroup(\n', 'class': 'ExceptionGroup'}, 'wrapping': [{'type': 'NameError', 'code': '4000', 'message': "NameError: name '__file__' is not defined", 'detail': {'args': '("name \'__file__\' is not defined",)', 'name': '__file__', 'traceback': '  File "/usr/lib/python3.12/site-packages/starlette/middleware/base.py", line 108, in __call__\n    response = await self.dispatch_func(request, call_next)\n               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\n\n  File "/usr/lib/python3.12/site-packages/server_utils/fastapi_utils/server_timing_middleware.py", line 49, in middleware_function\n    response = await call_next(request)\n               ^^^^^^^^^^^^^^^^^^^^^^^^\n\n  File "/usr/lib/python3.12/site-packages/starlette/middleware/base.py", line 84, in call_next\n    raise app_exc\n\n  File "/usr/lib/python3.12/site-packages/starlette/middleware/base.py", line 70, in coro\n    await self.app(scope, receive_or_disconnect, send_no_error)\n\n  File "/usr/lib/python3.12/site-packages/starlette/middleware/cors.py", line 83, in __call__\n    await self.app(scope, receive, send)\n\n  File "/usr/lib/python3.12/site-packages/starlette/middleware/exceptions.py", line 79, in __call__\n    raise exc\n\n  File "/usr/lib/python3.12/site-packages/starlette/middleware/exceptions.py", line 68, in __call__\n    await self.app(scope, receive, sender)\n\n  File "/usr/lib/python3.12/site-packages/fastapi/middleware/asyncexitstack.py", line 20, in __call__\n    raise e\n\n  File "/usr/lib/python3.12/site-packages/fastapi/middleware/asyncexitstack.py", line 17, in __call__\n    await self.app(scope, receive, send)\n\n  File "/usr/lib/python3.12/site-packages/starlette/routing.py", line 718, in __call__\n    await route.handle(scope, receive, send)\n\n  File "/usr/lib/python3.12/site-packages/starlette/routing.py", line 276, in handle\n    await self.app(scope, receive, send)\n\n  File "/usr/lib/python3.12/site-packages/starlette/routing.py", line 66, in app\n    response = await func(request)\n               ^^^^^^^^^^^^^^^^^^^\n\n  File "/usr/lib/python3.12/site-packages/fastapi/routing.py", line 273, in app\n    raw_response = await run_endpoint_function(\n                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^\n\n  File "/usr/lib/python3.12/site-packages/fastapi/routing.py", line 190, in run_endpoint_function\n    return await dependant.call(**values)\n           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\n\n  File "/usr/lib/python3.12/site-packages/robot_server/runs/router/base_router.py", line 262, in create_run\n    run_data = await run_data_manager.create(\n               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\n\n  File "/usr/lib/python3.12/site-packages/robot_server/runs/run_data_manager.py", line 256, in create\n    state_summary = await self._run_orchestrator_store.create(\n                    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\n\n  File "/usr/lib/python3.12/site-packages/robot_server/runs/run_orchestrator_store.py", line 303, in create\n    await orchestrator.load(\n\n  File "/usr/lib/python3.12/site-packages/opentrons/protocol_runner/run_orchestrator.py", line 481, in load\n    await self._protocol_runner.load(\n\n  File "/usr/lib/python3.12/site-packages/opentrons/protocol_runner/protocol_runner.py", line 218, in load\n    self._protocol_executor.extract_run_parameters(\n\n  File "/usr/lib/python3.12/site-packages/opentrons/protocol_runner/python_protocol_wrappers.py", line 172, in extract_run_parameters\n    return exec_add_parameters(\n           ^^^^^^^^^^^^^^^^^^^^\n\n  File "/usr/lib/python3.12/site-packages/opentrons/protocols/execution/execute_python.py", line 122, in exec_add_parameters\n    exec(protocol.contents, new_globs)\n\n  File "mara_perovskite.py", line 54, in <module>\n', 'class': 'NameError'}, 'wrapping': [{'type': 'EndOfStream', 'code': '4000', 'message': 'anyio.EndOfStream', 'detail': {'args': '()', 'traceback': '  File "/usr/lib/python3.12/site-packages/starlette/middleware/base.py", line 78, in call_next\n    message = await recv_stream.receive()\n              ^^^^^^^^^^^^^^^^^^^^^^^^^^^\n\n  File "/usr/lib/python3.12/site-packages/anyio/streams/memory.py", line 126, in receive\n    raise EndOfStream from None\n', 'class': 'EndOfStream'}, 'wrapping': [{'type': 'AttributeError', 'code': '4000', 'message': "AttributeError: 'MemoryObjectItemReceiver' object has no attribute 'item'", 'detail': {'args': '("\'MemoryObjectItemReceiver\' object has no attribute \'item\'",)', 'name': 'item', 'obj': "MemoryObjectItemReceiver(task_info=AsyncIOTaskInfo(id=1829921848, name='Task-253600'), item=None)", 'traceback': '  File "/usr/lib/python3.12/site-packages/anyio/streams/memory.py", line 124, in receive\n    return receiver.item\n           ^^^^^^^^^^^^^\n', 'class': 'AttributeError'}, 'wrapping': [{'type': 'WouldBlock', 'code': '4000', 'message': 'anyio.WouldBlock', 'detail': {'args': '()', 'traceback': '  File "/usr/lib/python3.12/site-packages/anyio/streams/memory.py", line 111, in receive\n    return self.receive_nowait()\n           ^^^^^^^^^^^^^^^^^^^^^\n\n  File "/usr/lib/python3.12/site-packages/anyio/streams/memory.py", line 106, in receive_nowait\n    raise WouldBlock\n', 'class': 'WouldBlock'}, 'wrapping': []}]}]}]}]}, 'errorCode': '4000'}]}