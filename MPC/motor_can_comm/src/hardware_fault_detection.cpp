#include <Arduino.h>

#include "hardware_fault_detection.h"
#include "robot_config.h"

bool hfdCanStartMove(const MotorControlStatus &status,
                      uint32_t now) {
    if (!status.leftHasStatus || !status.rightHasStatus ||
        now - status.leftLastStatusMs > TELEMETRY_TIMEOUT_MS ||
        now - status.rightLastStatusMs > TELEMETRY_TIMEOUT_MS) {
        Serial.println("waiting for fresh RPM status from both VESCs");
        return false;
    }
    return true;
}

const char *hfdGetActiveFault(
    const MotorControlStatus &status, uint32_t now) {
    if (!status.motionActive && !status.manualControlActive) {
        return nullptr;
    }
    if (status.motionActive &&
        now - status.motionStartMs > status.motionTimeoutMs) {
        return "motion timed out before reaching the target";
    }
    if (now - status.leftLastStatusMs > TELEMETRY_TIMEOUT_MS ||
        now - status.rightLastStatusMs > TELEMETRY_TIMEOUT_MS) {
        return "RPM telemetry timed out";
    }
    return nullptr;
}
