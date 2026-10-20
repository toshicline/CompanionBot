#pragma once

#include "motor_control.h"

bool hfdCanStartMove(const MotorControlStatus &status,
                      uint32_t now);
const char *hfdGetActiveFault(
    const MotorControlStatus &status, uint32_t now);
