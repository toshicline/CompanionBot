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
char uartLine[SERIAL_LINE_SIZE];
size_t uartLineLength = 0;
bool serialConnectionReported = false;

bool parseFiniteFloat(char *text, float &value) {
    char *end = nullptr;
    const float parsed = strtof(text, &end);
    if (text == end || *end != '\0' || !isfinite(parsed)) {
        return false;
    }
    value = parsed;
    return true;
}

void printHelp(Stream &port) {
    port.println("Commands:");
    port.println("  move <distance_m> <angle_deg>");
    port.println("  test <left_speed_mps> <right_speed_mps>");
    port.println("  status");
    port.println("  stop");
    port.println("  help");
    port.println("Positive angle turns left (counter-clockwise).");
    port.println("Use 'test 0 0' to ramp test speeds down; 'stop' stops immediately.");
}

void printStatus(Stream &port) {
    const MotorControlStatus status = mcGetStatus();
    const uint32_t now = millis();
    if (!status.leftHasStatus || !status.rightHasStatus ||
        now - status.leftLastStatusMs > TELEMETRY_TIMEOUT_MS ||
        now - status.rightLastStatusMs > TELEMETRY_TIMEOUT_MS) {
        port.println("ERR,telemetry_stale");
        return;
    }

    port.print("STATUS,");
    port.print(status.odometryDistanceM, 3);
    port.print(',');
    port.println(status.odometryAngleDeg, 2);
}

void handleCommand(Stream &port, char *line) {
    char *context = nullptr;
    char *command = strtok_r(line, " \t", &context);
    if (command == nullptr) {
        return;
    }

    if (strcmp(command, "help") == 0) {
        printHelp(port);
    } else if (strcmp(command, "status") == 0) {
        printStatus(port);
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
            port.println("ERR,usage_test,left_speed_mps,right_speed_mps");
            return;
        }
        if (fabsf(leftSpeedMps) > MAX_WHEEL_SPEED_MPS ||
            fabsf(rightSpeedMps) > MAX_WHEEL_SPEED_MPS) {
            port.println("ERR,test_speed_exceeds_limit");
            return;
        }
        if (hfdCanStartMove(mcGetStatus(), millis())) {
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
            port.println("ERR,usage_move,distance_m,angle_deg");
            return;
        }
        if (fabsf(distanceM) > MAX_DISTANCE_M ||
            fabsf(angleDeg) > MAX_ANGLE_DEG) {
            port.println("ERR,move_exceeds_limit");
            return;
        }
        if (hfdCanStartMove(mcGetStatus(), millis())) {
            mcBeginMove(distanceM, angleDeg);
        }
    } else {
        port.println("ERR,unknown_command");
    }
}

void readSerialInput(Stream &port, char *line, size_t &lineLength) {
    while (port.available() > 0) {
        const char incoming = static_cast<char>(port.read());
        if (incoming == '\r') {
            continue;
        }
        if (incoming == '\n') {
            line[lineLength] = '\0';
            handleCommand(port, line);
            lineLength = 0;
        } else if (lineLength < SERIAL_LINE_SIZE - 1) {
            line[lineLength++] = incoming;
        } else {
            lineLength = 0;
            port.println("ERR,input_line_too_long");
        }
    }
}

}

void setup() {
    Serial.begin(115200);
    Serial1.begin(115200);
    mcBegin();
}

void loop() {
    if (Serial && !serialConnectionReported) {
        Serial.println("USB serial monitor connected at 115200 baud.");
        printHelp(Serial);
        serialConnectionReported = true;
    }

    mcProcessCanMessages();
    readSerialInput(Serial, serialLine, serialLineLength);
    readSerialInput(Serial1, uartLine, uartLineLength);

    const char *fault =
        hfdGetActiveFault(mcGetStatus(), millis());
    if (fault != nullptr) {
        mcStop(fault);
    } else {
        mcUpdate();
    }
}
