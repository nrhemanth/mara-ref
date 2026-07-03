from heater_module.heater_control import IkaRct5
import time

with IkaRct5("COM4") as heater:
    print(heater.get_hotplate_temperature())  # current plate temp
    print(heater.get_setpoint_temperature())  # confirms target was set

    target = 50.0
    heater.set_setpoint_temperature(target)
    heater.start_heating()                  # actually starts heating

    while heater.get_hotplate_temperature() < target:
        time.sleep(2)

    heater.stop_heating()
