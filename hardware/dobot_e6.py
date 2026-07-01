"""TCP/IP control for a Dobot Magician E6 robot arm.

The E6 controller exposes Dobot's "TCP-IP-CR" protocol (shared with the
CR-series cobots) over two plain-text ASCII sockets:
  - port 29999 ("dashboard") -> enable/disable, clear errors, mode/pose queries
  - port 30003 ("motion")    -> MovJ / MovL / JointMovJ motion commands

Every command is a line like "EnableRobot()\\n" and the reply is a line like
"0,{},EnableRobot();\\n" where the leading integer is an error code (0 = ok).

Factory default network config on the controller is a static IP of
192.168.5.1 / 255.255.255.0, so set your PC's ethernet adapter to something
like 192.168.5.100/24 before connecting, unless it's been reconfigured
(check the "Ethernet" / network settings on the teach pendant or DobotStudio).
"""

import re
import socket

DASHBOARD_PORT = 29999
MOTION_PORT = 30003
TIMEOUT = 5


class DobotE6:
    def __init__(self, ip, timeout=TIMEOUT):
        self.ip = ip
        self.timeout = timeout
        self._dashboard = socket.create_connection((ip, DASHBOARD_PORT), timeout=timeout)
        self._motion = None  # opened lazily — not every session needs motion commands

    def close(self):
        self._dashboard.close()
        if self._motion is not None:
            self._motion.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    @staticmethod
    def _send(sock, command):
        sock.sendall(f"{command}\n".encode("ascii"))
        response = sock.recv(4096).decode("ascii", errors="replace").strip()
        error_id, _, _ = response.partition(",")
        if error_id.strip() not in ("0", ""):
            raise RuntimeError(f"{command} -> {response}")
        return response

    def _dashboard_cmd(self, command):
        return self._send(self._dashboard, command)

    def _motion_cmd(self, command):
        if self._motion is None:
            self._motion = socket.create_connection((self.ip, MOTION_PORT), timeout=self.timeout)
        return self._send(self._motion, command)

    # ------------------------------------------------------------------
    # Power / state
    # ------------------------------------------------------------------
    def enable(self):
        return self._dashboard_cmd("EnableRobot()")

    def disable(self):
        return self._dashboard_cmd("DisableRobot()")

    def clear_error(self):
        return self._dashboard_cmd("ClearError()")

    def reset(self):
        return self._dashboard_cmd("ResetRobot()")

    def emergency_stop(self):
        return self._dashboard_cmd("EmergencyStop()")

    def robot_mode(self):
        return self._dashboard_cmd("RobotMode()")

    def set_speed_factor(self, percent):
        return self._dashboard_cmd(f"SpeedFactor({round(percent)})")

    def set_tool(self, index):
        return self._dashboard_cmd(f"Tool({index})")

    def set_user(self, index):
        return self._dashboard_cmd(f"User({index})")

    def start_drag(self):
        """Enter drag/free-drive mode — servos stay compliant so the arm
        can be moved by hand (used for manual jogging / teaching points)."""
        return self._dashboard_cmd("StartDrag()")

    def stop_drag(self):
        """Exit drag mode and return to normal (stiff) servo control."""
        return self._dashboard_cmd("StopDrag()")

    # ------------------------------------------------------------------
    # Pose queries
    # ------------------------------------------------------------------
    def get_pose(self):
        """Cartesian pose as (x, y, z, rx, ry, rz) in mm / degrees."""
        return self._parse_floats(self._dashboard_cmd("GetPose()"))

    def get_angles(self):
        """Joint angles as (j1..j6) in degrees."""
        return self._parse_floats(self._dashboard_cmd("GetAngle()"))

    # ------------------------------------------------------------------
    # Motion
    # ------------------------------------------------------------------
    def move_joint(self, j1, j2, j3, j4, j5, j6):
        """Joint-space move (each axis interpolates independently)."""
        return self._motion_cmd(f"JointMovJ({j1},{j2},{j3},{j4},{j5},{j6})")

    def move_to_pose(self, x, y, z, rx, ry, rz):
        """Point-to-point Cartesian move (fastest path, not straight-line)."""
        return self._motion_cmd(f"MovJ({x},{y},{z},{rx},{ry},{rz})")

    def move_linear(self, x, y, z, rx, ry, rz):
        """Straight-line Cartesian move."""
        return self._motion_cmd(f"MovL({x},{y},{z},{rx},{ry},{rz})")

    def sync(self):
        """Block until all queued motion commands finish."""
        return self._motion_cmd("Sync()")

    @staticmethod
    def _parse_floats(response):
        # Reply looks like "0,{1.0,2.0,3.0,4.0,5.0,6.0},GetPose();"
        match = re.search(r"\{([^}]*)\}", response)
        return tuple(float(v) for v in match.group(1).split(","))


if __name__ == "__main__":
    import sys

    ip = sys.argv[1] if len(sys.argv) > 1 else "192.168.5.1"
    with DobotE6(ip) as robot:
        print(robot.enable())
        print("Pose:", robot.get_pose())
        print("Angles:", robot.get_angles())

        print(robot.start_drag())
        print("Drag mode on — the arm should now move freely by hand.")
        input("Press Enter to exit drag mode...")
        print(robot.stop_drag())

        print(robot.disable())
