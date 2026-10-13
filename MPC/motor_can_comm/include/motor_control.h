#pragma once

#include <Arduino.h>

struct MotorControlStatus {
    uint32_t leftLastStatusMs;
    uint32_t rightLastStatusMs;
    uint32_t motionStartMs;
    uint32_t motionTimeoutMs;
    bool leftHasStatus;
    bool rightHasStatus;
    bool motionActive;
    bool manualControlActive;
};

void mcBegin();
void mcProcessCanMessages();
void mcBeginMove(float distanceM, float angleDeg);
bool mcSetWheelSpeeds(float leftSpeedMps, float rightSpeedMps);
void mcUpdate();
void mcStop(const char *reason);
MotorControlStatus mcGetStatus();
