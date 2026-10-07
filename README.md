# Teensy 4.1 Dual VESC CAN Motion Controller

PlatformIO firmware for terminal-driven differential-drive motion using two
VESC-compatible controllers, such as a Dual FSESC 4.20A.

## Project layout

The PlatformIO project files (`platformio.ini`, `.vscode`, and `.pio`) are in
this folder. Motor-control source and headers are kept in
`motor_can_comm/src` and `motor_can_comm/include`.

## Hardware and safety

- Teensy 4.1 has CAN controllers but needs an external CAN transceiver. Connect
  CAN1 TX (Teensy pin 22) and RX (pin 23) to a 3.3 V-compatible transceiver,
  then connect CANH/CANL to the ESC CAN bus with the bus properly terminated.
- The firmware assumes VESC CAN at 500 kbit/s, VESC-compatible extended CAN
  frames, and CAN IDs that are individually addressable for each motor.
- Configure the IDs and drivetrain constants in
  `motor_can_comm/include/robot_config.h`. In particular, measure wheel
  circumference and track width, and set the motor pole-pair count, gear ratio,
  and direction signs for your assembly.
- The two controllers must broadcast VESC STATUS frames containing ERPM
  (packet type 9 / STATUS). The firmware refuses to start without recent
  status from both controllers and sends zero RPM if status becomes stale.
- Test with the drive wheels raised and a hardware emergency stop available.
  RPM integration provides an estimate of travel, not a safety-rated position
  measurement. Tune the speed limit and verify motor direction before
  operating on the ground.


## Terminal commands

```text
move <distance_m> <angle_deg>
stop
help
```

For example, `move 1.0 0` requests one meter straight ahead. `move 0 90`
requests a 90-degree in-place counter-clockwise turn. Positive angles turn
left. A combined distance and angle follows differential-drive arc kinematics.
Negative distance or angle is supported.
