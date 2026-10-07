#include <Arduino.h>
#include <FlexCAN_T4.h>
#include <cmath>
#include <cstdlib>
#include <cstring>

#include "robot_config.h"

namespace {

constexpr uint8_t CAN_PACKET_SET_RPM = 3;
constexpr uint8_t CAN_PACKET_STATUS = 9;
constexpr uint32_t CAN_BAUD_RATE = 500000;
constexpr uint32_t MOTION_TIMEOUT_MARGIN_MS = 5000;
constexpr float MOTION_TIMEOUT_FACTOR = 3.0f;
constexpr size_t SERIAL_LINE_SIZE = 96;

static_assert(LEFT_VESC_CAN_ID != RIGHT_VESC_CAN_ID,
              "The left and right VESC CAN IDs must be different.");

FlexCAN_T4<CAN1, RX_SIZE_256, TX_SIZE_16> Can0;

struct WheelState {
    uint8_t canId;
    int8_t direction;
    float targetDistanceM = 0.0f;
    float measuredDistanceM = 0.0f;
    float measuredErpm = 0.0f;
    uint32_t lastStatusMs = 0;
    bool hasStatus = false;
    bool complete = false;
};

WheelState leftWheel{LEFT_VESC_CAN_ID, LEFT_MOTOR_DIRECTION};
WheelState rightWheel{RIGHT_VESC_CAN_ID, RIGHT_MOTOR_DIRECTION};
bool motionActive = false;
uint32_t lastCommandMs = 0;
uint32_t motionStartMs = 0;
uint32_t motionTimeoutMs = 0;
char serialLine[SERIAL_LINE_SIZE];
size_t serialLineLength = 0;

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

void stopMotion(const char *reason) {
    sendRpmCommand(leftWheel, 0.0f);
    sendRpmCommand(rightWheel, 0.0f);
    motionActive = false;
    Serial.print("Stopped: ");
    Serial.println(reason);
}

float remainingDistance(const WheelState &wheel) {
    return wheel.targetDistanceM - wheel.measuredDistanceM;
}

bool targetReached(const WheelState &wheel) {
    if (fabsf(wheel.targetDistanceM) < 0.0001f) {
        return true;
    }
    return remainingDistance(wheel) * wheel.targetDistanceM <= 0.0f;
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

    if (motionActive && wheel->hasStatus) {
        const uint32_t elapsedMs = now - wheel->lastStatusMs;
        if (elapsedMs <= TELEMETRY_TIMEOUT_MS) {
            const float wheelRpm =
                wheel->measuredErpm / (MOTOR_POLE_PAIRS * GEAR_RATIO);
            wheel->measuredDistanceM +=
                wheelRpm * (WHEEL_CIRCUMFERENCE_M / 60.0f) *
                (static_cast<float>(elapsedMs) / 1000.0f);
        }
    }

    wheel->measuredErpm =
        static_cast<float>(motorErpm) * static_cast<float>(wheel->direction);
    wheel->lastStatusMs = now;
    wheel->hasStatus = true;
}

void drainCanMessages() {
    CAN_message_t message;
    while (Can0.read(message)) {
        processStatusFrame(message);
    }
}

bool parseFiniteFloat(char *text, float &value) {
    char *end = nullptr;
    const float parsed = strtof(text, &end);
    if (text == end || *end != '\0' || !isfinite(parsed)) {
        return false;
    }
    value = parsed;
    return true;
}

void printHelp() {
    Serial.println("Commands:");
    Serial.println("  move <distance_m> <angle_deg>");
    Serial.println("  stop");
    Serial.println("  help");
    Serial.println("Positive angle turns left (counter-clockwise).");
}

void beginMove(float distanceM, float angleDeg) {
    const uint32_t now = millis();
    if (!leftWheel.hasStatus || !rightWheel.hasStatus ||
        now - leftWheel.lastStatusMs > TELEMETRY_TIMEOUT_MS ||
        now - rightWheel.lastStatusMs > TELEMETRY_TIMEOUT_MS) {
        Serial.println(
            "Error: waiting for fresh RPM status from both VESCs. "
            "Check CAN IDs and VESC CAN status broadcasts.");
        return;
    }

    const float angleRad = angleDeg * PI / 180.0f;
    leftWheel.targetDistanceM =
        distanceM - angleRad * TRACK_WIDTH_M * 0.5f;
    rightWheel.targetDistanceM =
        distanceM + angleRad * TRACK_WIDTH_M * 0.5f;
    leftWheel.measuredDistanceM = 0.0f;
    rightWheel.measuredDistanceM = 0.0f;
    leftWheel.complete = fabsf(leftWheel.targetDistanceM) < 0.0001f;
    rightWheel.complete = fabsf(rightWheel.targetDistanceM) < 0.0001f;
    motionActive = !leftWheel.complete || !rightWheel.complete;
    lastCommandMs = 0;
    motionStartMs = now;
    leftWheel.lastStatusMs = now;
    rightWheel.lastStatusMs = now;
    leftWheel.measuredErpm = 0.0f;
    rightWheel.measuredErpm = 0.0f;

    if (!motionActive) {
        sendRpmCommand(leftWheel, 0.0f);
        sendRpmCommand(rightWheel, 0.0f);
        Serial.println("Move complete: requested motion is zero.");
        return;
    }

    Serial.print("Moving. Left target: ");
    Serial.print(leftWheel.targetDistanceM, 3);
    Serial.print(" m; right target: ");
    Serial.print(rightWheel.targetDistanceM, 3);
    Serial.println(" m.");
    const float longestWheelTravel =
        fmaxf(fabsf(leftWheel.targetDistanceM),
              fabsf(rightWheel.targetDistanceM));
    const float nominalDurationMs =
        longestWheelTravel / MAX_WHEEL_SPEED_MPS * 1000.0f;
    motionTimeoutMs = static_cast<uint32_t>(
        nominalDurationMs * MOTION_TIMEOUT_FACTOR +
        static_cast<float>(MOTION_TIMEOUT_MARGIN_MS));
}

void handleCommand(char *line) {
    char *context = nullptr;
    char *command = strtok_r(line, " \t", &context);
    if (command == nullptr) {
        return;
    }

    if (strcmp(command, "help") == 0) {
        printHelp();
    } else if (strcmp(command, "stop") == 0) {
        stopMotion("terminal command");
    } else if (strcmp(command, "move") == 0) {
        char *distanceText = strtok_r(nullptr, " \t", &context);
        char *angleText = strtok_r(nullptr, " \t", &context);
        char *extra = strtok_r(nullptr, " \t", &context);
        float distanceM = 0.0f;
        float angleDeg = 0.0f;
        if (distanceText == nullptr || angleText == nullptr || extra != nullptr ||
            !parseFiniteFloat(distanceText, distanceM) ||
            !parseFiniteFloat(angleText, angleDeg)) {
            Serial.println("Usage: move <distance_m> <angle_deg>");
            return;
        }
        if (fabsf(distanceM) > MAX_DISTANCE_M ||
            fabsf(angleDeg) > MAX_ANGLE_DEG) {
            Serial.println("Error: request exceeds configured motion limits.");
            return;
        }
        if (motionActive) {
            stopMotion("new move command");
        }
        beginMove(distanceM, angleDeg);
    } else {
        Serial.println("Unknown command. Type 'help'.");
    }
}

void readSerialInput() {
    while (Serial.available() > 0) {
        const char incoming = static_cast<char>(Serial.read());
        if (incoming == '\r') {
            continue;
        }
        if (incoming == '\n') {
            serialLine[serialLineLength] = '\0';
            handleCommand(serialLine);
            serialLineLength = 0;
        } else if (serialLineLength < SERIAL_LINE_SIZE - 1) {
            serialLine[serialLineLength++] = incoming;
        } else {
            serialLineLength = 0;
            Serial.println("Error: input line too long.");
        }
    }
}

void updateMotion() {
    if (!motionActive) {
        return;
    }

    const uint32_t now = millis();
    if (now - motionStartMs > motionTimeoutMs) {
        stopMotion("motion timed out before reaching the target");
        return;
    }
    if (now - leftWheel.lastStatusMs > TELEMETRY_TIMEOUT_MS ||
        now - rightWheel.lastStatusMs > TELEMETRY_TIMEOUT_MS) {
        stopMotion("RPM telemetry timed out");
        return;
    }

    leftWheel.complete = leftWheel.complete || targetReached(leftWheel);
    rightWheel.complete = rightWheel.complete || targetReached(rightWheel);
    if (leftWheel.complete && rightWheel.complete) {
        stopMotion("distance and angle reached");
        return;
    }
    if (now - lastCommandMs < CAN_COMMAND_PERIOD_MS) {
        return;
    }

    const float maxTargetDistance =
        fmaxf(fabsf(leftWheel.targetDistanceM),
              fabsf(rightWheel.targetDistanceM));
    const float leftSpeed = leftWheel.complete
                                ? 0.0f
                                : copysignf(MAX_WHEEL_SPEED_MPS *
                                                fabsf(leftWheel.targetDistanceM) /
                                                maxTargetDistance,
                                            leftWheel.targetDistanceM);
    const float rightSpeed = rightWheel.complete
                                 ? 0.0f
                                 : copysignf(MAX_WHEEL_SPEED_MPS *
                                                 fabsf(rightWheel.targetDistanceM) /
                                                 maxTargetDistance,
                                             rightWheel.targetDistanceM);
    sendRpmCommand(leftWheel, motorErpmFromWheelSpeed(leftSpeed));
    sendRpmCommand(rightWheel, motorErpmFromWheelSpeed(rightSpeed));
    lastCommandMs = now;
}

}  // namespace

void setup() {
    Serial.begin(115200);

    Can0.begin();
    Can0.setBaudRate(CAN_BAUD_RATE);
    Can0.setMaxMB(16);
    Can0.enableFIFO();

    Serial.println("Teensy 4.1 differential-drive VESC CAN controller ready.");
    Serial.println("Waiting for VESC RPM status; type 'help' for commands.");
}

void loop() {
    drainCanMessages();
    readSerialInput();
    updateMotion();
}
