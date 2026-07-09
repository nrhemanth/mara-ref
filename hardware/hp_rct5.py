#hp rct5 (Hot plate, IKA RCT5)

"""Serial control for an IKA RCT 5 hotplate stirrer.

IKA RCT 5 units speak IKA's standard RS232 "NAMUR" command protocol
(the same command set used across the RCT/RET/Big Squid lines):
  - 9600 baud, 7 data bits, even parity, 1 stop bit, no flow control
  - commands are ASCII, terminated with CR LF ("\\r\\n")
  - temperature values are plain decimal degrees C (e.g. "50.0"), not tenths

Reference command set:
  IN_NAME                -> read device name
  IN_PV_1                -> read current hotplate (sensor) temperature
  IN_PV_2                -> read current medium/probe temperature (if PT1000 connected)
  IN_PV_4                -> read current stirring speed
  IN_SP_1                -> read hotplate setpoint temperature
  IN_SP_4                -> read stirring speed setpoint
  OUT_SP_1 <value>       -> set hotplate setpoint temperature (decimal C, e.g. "50.0")
  OUT_SP_4 <value>       -> set stirring speed setpoint (rpm)
  START_1 / STOP_1       -> start/stop heating
  START_4 / STOP_4       -> start/stop stirring
  RESET                  -> return control to the front panel
"""

import serial

BAUDRATE = 9600
BYTESIZE = serial.SEVENBITS
PARITY = serial.PARITY_EVEN
STOPBITS = serial.STOPBITS_ONE
TIMEOUT = 2


class IkaRct5:
    def __init__(self, port, timeout=TIMEOUT):
        self._serial = serial.Serial(
            port=port,
            baudrate=BAUDRATE,
            bytesize=BYTESIZE,
            parity=PARITY,
            stopbits=STOPBITS,
            timeout=timeout,
        )

    def close(self):
        self._serial.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def _send(self, command):
        self._serial.write(f"{command}\r\n".encode("ascii"))

    def _query(self, command):
        self._serial.reset_input_buffer()
        self._send(command)
        response = self._serial.readline().decode("ascii", errors="replace").strip()
        return response

    def get_name(self):
        return self._query("IN_NAME")

    def get_hotplate_temperature(self):
        return self._parse_temperature(self._query("IN_PV_1"))

    def get_medium_temperature(self):
        return self._parse_temperature(self._query("IN_PV_2"))

    def get_setpoint_temperature(self):
        return self._parse_temperature(self._query("IN_SP_1"))

    def set_setpoint_temperature(self, celsius):
        self._send(f"OUT_SP_1 {celsius:.1f}")

    def start_heating(self):
        self._send("START_1")

    def stop_heating(self):
        self._send("STOP_1")

    def start_stirring(self):
        self._send("START_4")

    def stop_stirring(self):
        self._send("STOP_4")

    def set_stirring_speed(self, rpm):
        self._send(f"OUT_SP_4 {round(rpm)}")

    @staticmethod
    def _parse_temperature(response):
        # Reply looks like "50.0 1" (value, sensor number)
        return float(response.split()[0])


if __name__ == "__main__":
    import sys

    port = sys.argv[1] if len(sys.argv) > 1 else "COM4"
    with IkaRct5(port) as heater:
        print("Device name:", heater.get_name())
        print("Hotplate temperature:", heater.get_hotplate_temperature())



