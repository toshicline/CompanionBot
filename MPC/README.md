# Teensy 4.1 Hardware Abstraction Layer

PlatformIO firmware for terminal-driven differential-drive motion using a Dual FSESC 4.20A motor controller and JKBMS 

## Project layout

The PlatformIO project files (`platformio.ini`, `.vscode`, and `.pio`) are in this folder.

- `motor_control.cpp` owns VESC CAN communication and wheel motion control.
- `hardware_fault_detection.cpp` checks for fresh motor telemetry before motion and stops active motion if telemetry or the motion deadline times out.
- `main.cpp` handles serial commands and calls both modules.

## Terminal commands

- `move <distance_m> <angle_deg>`
- `test <left_speed_mps> <right_speed_mps>`
- `stop`
- `help`
