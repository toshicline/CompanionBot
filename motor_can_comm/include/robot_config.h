#pragma once

// Set these to the CAN IDs configured on the two VESCs.
constexpr uint8_t LEFT_VESC_CAN_ID = 1;
constexpr uint8_t RIGHT_VESC_CAN_ID = 2;

// Chassis and drivetrain calibration. Gear ratio is motor revolutions per
// wheel revolution; pole pairs converts motor RPM to electrical RPM.
constexpr float WHEEL_CIRCUMFERENCE_M = 0.30f;
constexpr float TRACK_WIDTH_M = 0.40f;
constexpr float MOTOR_POLE_PAIRS = 1.0f;
constexpr float GEAR_RATIO = 1.0f;

// Use -1 for a motor whose positive ERPM makes its wheel travel backward.
constexpr int8_t LEFT_MOTOR_DIRECTION = 1;
constexpr int8_t RIGHT_MOTOR_DIRECTION = 1;

constexpr float MAX_WHEEL_SPEED_MPS = 0.20f;
constexpr float MAX_DISTANCE_M = 5.0f;
constexpr float MAX_ANGLE_DEG = 720.0f;
constexpr uint32_t TELEMETRY_TIMEOUT_MS = 500;
constexpr uint32_t CAN_COMMAND_PERIOD_MS = 100;
