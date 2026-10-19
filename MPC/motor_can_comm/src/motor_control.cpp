#include <Arduino.h>
#include <FlexCAN_T4.h>
#include <cmath>

#include "motor_control.h"
#include "robot_config.h"

namespace {

constexpr uint8_t CAN_PACKET_SET_RPM = 3;
constexpr uint8_t CAN_PACKET_STATUS = 9;
constexpr uint32_t CAN_BAUD_RATE = 500000;
constexpr uint32_t MOTION_TIMEOUT_MARGIN_MS = 5000;
constexpr float MOTION_TIMEOUT_FACTOR = 3.0f;
constexpr float STOP_SPEED_TOLERANCE_MPS = 0.02f;

static_assert(LEFT_VESC_CAN_ID != RIGHT_VESC_CAN_ID,
              "The left and right VESC CAN IDs must be different.");

FlexCAN_T4<CAN1, RX_SIZE_256, TX_SIZE_16> Can0;

struct WheelState {
    uint8_t canId;
    int8_t direction;
    float targetDistanceM = 0.0f;
    float measuredDistanceM = 0.0f;
    float measuredErpm = 0.0f;
    float commandedSpeedMps = 0.0f;
    float odometryDistanceM = 0.0f;
    uint32_t lastStatusMs = 0;
    bool hasStatus = false;
    bool complete = false;
};

WheelState leftWheel{LEFT_VESC_CAN_ID, LEFT_MOTOR_DIRECTION};
WheelState rightWheel{RIGHT_VESC_CAN_ID, RIGHT_MOTOR_DIRECTION};
bool motionActive = false;
uint32_t lastCommandMs = 0;
uint32_t lastControlUpdateMs = 0;
uint32_t motionStartMs = 0;
uint32_t motionTimeoutMs = 0;
bool manualControlActive = false;
float manualLeftSpeedMps = 0.0f;
float manualRightSpeedMps = 0.0f;
float movePathDistanceM = 0.0f;
float movePathCommandedSpeedMps = 0.0f;

float motorErpmFromWheelSpeed(float wheelSpeedMps) {
    const float wheelRpm = wheelSpeedMps / WHEEL_CIRCUMFERENCE_M * 60.0f;
    return wheelRpm * MOTOR_POLE_PAIRS * GEAR_RATIO;
}

void sendRpmCommand(const WheelState &wheel, float wheelErpm) {
    const int32_t motorErpm = static_cast<int32_t>(
        lroundf(wheelErpm * static_cast<float>(wheel.direction)));
    const uint32_t canId =
        (static_cast<uint32_t>(CAN_PACKET_SET_RPM) << 8) | wheel.canId;

    CAN_message_t message;
    message.id = canId;
    message.flags.extended = 1;
    message.len = 4;
    message.buf[0] = static_cast<uint8_t>(motorErpm >> 24);
    message.buf[1] = static_cast<uint8_t>(motorErpm >> 16);
    message.buf[2] = static_cast<uint8_t>(motorErpm >> 8);
    message.buf[3] = static_cast<uint8_t>(motorErpm);
    if (!Can0.write(message)) {
        Serial.println("Error: CAN transmit queue is full.");
    }
}

float remainingDistance(const WheelState &wheel) {
    return wheel.targetDistanceM - wheel.measuredDistanceM;
}

float slewSpeed(float &currentSpeed, float targetSpeed, float elapsedSeconds) {
    const bool reversing = currentSpeed * targetSpeed < 0.0f;
    const float effectiveTarget = reversing ? 0.0f : targetSpeed;
    const bool accelerating = fabsf(effectiveTarget) > fabsf(currentSpeed);
    const float rate = accelerating ? MAX_WHEEL_ACCEL_MPS2 : MAX_WHEEL_DECEL_MPS2;
    const float maxChange = rate * elapsedSeconds;
    const float difference = effectiveTarget - currentSpeed;
    currentSpeed += fmaxf(-maxChange, fminf(maxChange, difference));
    return currentSpeed;
}

float remainingMovePathM() {
    float remaining = 0.0f;
    const WheelState *wheels[] = {&leftWheel, &rightWheel};
    for (const WheelState *wheel : wheels) {
        if (movePathDistanceM > 0.0f) {
            const float ratio = wheel->targetDistanceM / movePathDistanceM;
            if (fabsf(ratio) > 0.0001f) {
                const float wheelPathRemaining =
                    remainingDistance(*wheel) / ratio;
                if (wheelPathRemaining > remaining) {
                    remaining = wheelPathRemaining;
                }
            }
        }
    }
    return remaining;
}

float moveWheelSpeedTarget(const WheelState &wheel) {
    const float ratio = wheel.targetDistanceM / movePathDistanceM;
    if (fabsf(ratio) <= 0.0001f) {
        return 0.0f;
    }
    const float error = remainingDistance(wheel);
    if (error * wheel.targetDistanceM < 0.0f) {
        const float correction =
            fminf(MAX_WHEEL_SPEED_MPS, sqrtf(2.0f * MAX_WHEEL_DECEL_MPS2 * fabsf(error)));
        return error < 0.0f ? -correction : correction;
    }
    return ratio * movePathCommandedSpeedMps;
}

bool wheelReachedTarget(const WheelState &wheel) {
    return fabsf(remainingDistance(wheel)) <= POSITION_TOLERANCE_M && fabsf(wheel.commandedSpeedMps) <= STOP_SPEED_TOLERANCE_MPS;
}

void processStatusFrame(const CAN_message_t &message) {
    if (!message.flags.extended || message.len < 4) {
        return;
    }

    const uint8_t packetId = static_cast<uint8_t>((message.id >> 8) & 0xFF);
    const uint8_t controllerId = static_cast<uint8_t>(message.id & 0xFF);
    if (packetId != CAN_PACKET_STATUS) {
        return;
    }

    WheelState *wheel = nullptr;
    if (controllerId == leftWheel.canId) {
        wheel = &leftWheel;
    } else if (controllerId == rightWheel.canId) {
        wheel = &rightWheel;
    }
    if (wheel == nullptr) {
        return;
    }

    const int32_t motorErpm =
        (static_cast<int32_t>(message.buf[0]) << 24) |
        (static_cast<int32_t>(message.buf[1]) << 16) |
        (static_cast<int32_t>(message.buf[2]) << 8) |
        static_cast<int32_t>(message.buf[3]);
    const uint32_t now = millis();

    if (wheel->hasStatus) {
        const uint32_t elapsedMs = now - wheel->lastStatusMs;
        if (elapsedMs <= TELEMETRY_TIMEOUT_MS) {
            const float wheelRpm =
                wheel->measuredErpm / (MOTOR_POLE_PAIRS * GEAR_RATIO);
            const float traveledM =
                wheelRpm * (WHEEL_CIRCUMFERENCE_M / 60.0f) *
                (static_cast<float>(elapsedMs) / 1000.0f);
            wheel->odometryDistanceM += traveledM;
            if (motionActive) {
                wheel->measuredDistanceM += traveledM;
            }
        }
    }

    wheel->measuredErpm = static_cast<float>(motorErpm) * static_cast<float>(wheel->direction);
    wheel->lastStatusMs = now;
    wheel->hasStatus = true;
}

}

void mcBeginMove(float distanceM, float angleDeg) {
    const uint32_t now = millis();
    const float angleRad = angleDeg * PI / 180.0f;
    leftWheel.targetDistanceM = distanceM - angleRad * TRACK_WIDTH_M * 0.5f;
    rightWheel.targetDistanceM = distanceM + angleRad * TRACK_WIDTH_M * 0.5f;
    
    movePathDistanceM = fmaxf(fabsf(leftWheel.targetDistanceM), fabsf(rightWheel.targetDistanceM));
    movePathCommandedSpeedMps = 0.0f;
    
    leftWheel.measuredDistanceM = 0.0f;
    rightWheel.measuredDistanceM = 0.0f;
    leftWheel.complete = 
        fabsf(leftWheel.targetDistanceM) <= POSITION_TOLERANCE_M &&
        fabsf(leftWheel.commandedSpeedMps) <= STOP_SPEED_TOLERANCE_MPS;
    rightWheel.complete =
        fabsf(rightWheel.targetDistanceM) <= POSITION_TOLERANCE_M &&
        fabsf(rightWheel.commandedSpeedMps) <= STOP_SPEED_TOLERANCE_MPS;
    
    motionActive = !leftWheel.complete || !rightWheel.complete;
    manualControlActive = false;
    manualLeftSpeedMps = 0.0f;
    manualRightSpeedMps = 0.0f;
    lastCommandMs = 0;
    lastControlUpdateMs = now;
    motionStartMs = now;

    if (movePathDistanceM <= POSITION_TOLERANCE_M) {
        motionActive = false;
        manualControlActive = true;
        manualLeftSpeedMps = 0.0f;
        manualRightSpeedMps = 0.0f;
        lastCommandMs = now;
        lastControlUpdateMs = now;
        Serial.println("Zero-distance move; ramping wheel speeds down.");
        return;
    }

    if (!motionActive) {
        mcStop("requested motion is zero");
        return;
    }

    Serial.print("Moving. Left target: ");
    Serial.print(leftWheel.targetDistanceM, 3);
    Serial.print(" m; right target: ");
    Serial.print(rightWheel.targetDistanceM, 3);
    Serial.println(" m.");
    const float longestWheelTravel = movePathDistanceM;
    const float rampDistance =
        MAX_WHEEL_SPEED_MPS * MAX_WHEEL_SPEED_MPS /
        MAX_WHEEL_ACCEL_MPS2;
    const float nominalDurationSeconds =
        longestWheelTravel <= rampDistance
            ? 2.0f * sqrtf(longestWheelTravel / MAX_WHEEL_ACCEL_MPS2)
            : 2.0f * MAX_WHEEL_SPEED_MPS / MAX_WHEEL_ACCEL_MPS2 +
                  (longestWheelTravel - rampDistance) / MAX_WHEEL_SPEED_MPS;
    motionTimeoutMs = static_cast<uint32_t>(
        nominalDurationSeconds * 1000.0f * MOTION_TIMEOUT_FACTOR +
        static_cast<float>(MOTION_TIMEOUT_MARGIN_MS));
}

void mcBegin() {
    Can0.begin();
    Can0.setBaudRate(CAN_BAUD_RATE);
    Can0.setMaxMB(16);
    Can0.enableFIFO();
}

void mcProcessCanMessages() {
    CAN_message_t message;
    while (Can0.read(message)) {
        processStatusFrame(message);
    }
}


bool mcSetWheelSpeeds(float leftSpeedMps, float rightSpeedMps) {
    if (!isfinite(leftSpeedMps) || !isfinite(rightSpeedMps) ||
        fabsf(leftSpeedMps) > MAX_WHEEL_SPEED_MPS ||
        fabsf(rightSpeedMps) > MAX_WHEEL_SPEED_MPS) {
        Serial.println(
            "Error: test wheel speeds must be finite and within the configured "
            "speed limit.");
        return false;
    }

    motionActive = false;
    manualControlActive = true;
    manualLeftSpeedMps = leftSpeedMps;
    manualRightSpeedMps = rightSpeedMps;
    lastCommandMs = millis();
    lastControlUpdateMs = lastCommandMs;
    Serial.println("Test speed targets set; ramping wheel speeds.");
    return true;
}

void mcStop(const char *reason) {
    sendRpmCommand(leftWheel, 0.0f);
    sendRpmCommand(rightWheel, 0.0f);
    motionActive = false;
    manualControlActive = false;
    manualLeftSpeedMps = 0.0f;
    manualRightSpeedMps = 0.0f;
    leftWheel.commandedSpeedMps = 0.0f;
    rightWheel.commandedSpeedMps = 0.0f;
    movePathCommandedSpeedMps = 0.0f;
    Serial.print("Stopped: ");
    Serial.println(reason);
}

void mcUpdate() {
    const uint32_t now = millis();
    if (manualControlActive) {
        if (now - lastCommandMs >= CAN_COMMAND_PERIOD_MS) {
            const float elapsedSeconds =
                static_cast<float>(now - lastControlUpdateMs) / 1000.0f;
            lastControlUpdateMs = now;
            const float leftSpeed = slewSpeed(
                leftWheel.commandedSpeedMps, manualLeftSpeedMps,
                elapsedSeconds);
            const float rightSpeed = slewSpeed(
                rightWheel.commandedSpeedMps, manualRightSpeedMps,
                elapsedSeconds);
            sendRpmCommand(leftWheel, motorErpmFromWheelSpeed(leftSpeed));
            sendRpmCommand(rightWheel, motorErpmFromWheelSpeed(rightSpeed));
            lastCommandMs = now;
            if (manualLeftSpeedMps == 0.0f &&
                manualRightSpeedMps == 0.0f &&
                fabsf(leftSpeed) <= STOP_SPEED_TOLERANCE_MPS &&
                fabsf(rightSpeed) <= STOP_SPEED_TOLERANCE_MPS) {
                mcStop("test ramp-down complete");
            }
        }
        return;
    }
    if (!motionActive) {
        return;
    }

    leftWheel.complete = leftWheel.complete || wheelReachedTarget(leftWheel);
    rightWheel.complete = rightWheel.complete || wheelReachedTarget(rightWheel);
    if (leftWheel.complete && rightWheel.complete) {
        mcStop("distance and angle reached");
        return;
    }
    if (now - lastCommandMs < CAN_COMMAND_PERIOD_MS) {
        return;
    }

    const float elapsedSeconds = static_cast<float>(now - lastControlUpdateMs) / 1000.0f;
    lastControlUpdateMs = now;
    
    const float remainingPath = remainingMovePathM();
    const float pathStoppingSpeed = sqrtf(2.0f * MAX_WHEEL_DECEL_MPS2 * remainingPath);
    const float pathTargetSpeed = fminf(MAX_WHEEL_SPEED_MPS, pathStoppingSpeed);
    
    movePathCommandedSpeedMps = slewSpeed(movePathCommandedSpeedMps, pathTargetSpeed, elapsedSeconds);
    const float leftSpeed = leftWheel.complete ? 0.0f : moveWheelSpeedTarget(leftWheel);
    const float rightSpeed = rightWheel.complete ? 0.0f : moveWheelSpeedTarget(rightWheel);
    const float leftCommand = slewSpeed(leftWheel.commandedSpeedMps, leftSpeed, elapsedSeconds);
    const float rightCommand = slewSpeed(rightWheel.commandedSpeedMps, rightSpeed, elapsedSeconds);
    
    sendRpmCommand(leftWheel, motorErpmFromWheelSpeed(leftCommand));
    sendRpmCommand(rightWheel, motorErpmFromWheelSpeed(rightCommand));
    lastCommandMs = now;
}

MotorControlStatus mcGetStatus() {
    const float distanceM =
        (leftWheel.odometryDistanceM + rightWheel.odometryDistanceM) * 0.5f;
    const float angleDeg =
        (rightWheel.odometryDistanceM - leftWheel.odometryDistanceM) /
        TRACK_WIDTH_M * 180.0f / PI;
    return {
        leftWheel.lastStatusMs,
        rightWheel.lastStatusMs,
        motionStartMs,
        motionTimeoutMs,
        leftWheel.hasStatus,
        rightWheel.hasStatus,
        motionActive,
        manualControlActive,
        distanceM,
        angleDeg,
    };
}
