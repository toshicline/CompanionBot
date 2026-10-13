#include <Arduino.h>
#include <cmath>
#include <cstdlib>
#include <cstring>

#include "hardware_fault_detection.h"
#include "motor_control.h"
#include "robot_config.h"

namespace {

constexpr size_t SERIAL_LINE_SIZE = 96;

char serialLine[SERIAL_LINE_SIZE];
size_t serialLineLength = 0;

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
    Serial.println("  test <left_speed_mps> <right_speed_mps>");
    Serial.println("  stop");
    Serial.println("  help");
    Serial.println("Positive angle turns left (counter-clockwise).");
    Serial.println("Test wheel speeds remain active until 'stop' is entered.");
}

void stopActiveControl(const char *reason) {
    const MotorControlStatus status = mcGetStatus();
    if (status.motionActive || status.manualControlActive) {
        mcStop(reason);
    }
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
        mcStop("terminal command");
    } else if (strcmp(command, "test") == 0) {
        char *leftSpeedText = strtok_r(nullptr, " \t", &context);
        char *rightSpeedText = strtok_r(nullptr, " \t", &context);
        char *extra = strtok_r(nullptr, " \t", &context);
        float leftSpeedMps = 0.0f;
        float rightSpeedMps = 0.0f;
        if (leftSpeedText == nullptr || rightSpeedText == nullptr ||
            extra != nullptr ||
            !parseFiniteFloat(leftSpeedText, leftSpeedMps) ||
            !parseFiniteFloat(rightSpeedText, rightSpeedMps)) {
            Serial.println("Usage: test <left_speed_mps> <right_speed_mps>");
            return;
        }
        if (fabsf(leftSpeedMps) > MAX_WHEEL_SPEED_MPS ||
            fabsf(rightSpeedMps) > MAX_WHEEL_SPEED_MPS) {
            Serial.println("Error: test speed exceeds the configured limit.");
            return;
        }
        stopActiveControl("new test command");
        if (hfdCanStartMove(mcGetStatus(),
                                               millis())) {
            mcSetWheelSpeeds(leftSpeedMps, rightSpeedMps);
        }
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
        stopActiveControl("new move command");
        if (hfdCanStartMove(mcGetStatus(),
                                               millis())) {
            mcBeginMove(distanceM, angleDeg);
        }
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

}  // namespace

void setup() {
    Serial.begin(115200);
    mcBegin();

    Serial.println("Teensy 4.1 differential-drive VESC CAN controller ready.");
    Serial.println("Waiting for VESC RPM status; type 'help' for commands.");
}

void loop() {
    mcProcessCanMessages();
    readSerialInput();

    const char *fault =
        hfdGetActiveFault(mcGetStatus(), millis());
    if (fault != nullptr) {
        mcStop(fault);
    } else {
        mcUpdate();
    }
}
