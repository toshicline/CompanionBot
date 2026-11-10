import Jetson.GPIO as GPIO
import time

SOUND_PIN = 7  # BOARD Pin 7

GPIO.setmode(GPIO.BOARD)
GPIO.setup(SOUND_PIN, GPIO.IN)

print("Listening for sound... Press Ctrl+C to exit.")
try:
    while True:
        if GPIO.input(SOUND_PIN) == GPIO.HIGH:
            print("Sound threshold exceeded!")
            time.sleep(0.2)  # Short debounce delay
        time.sleep(0.01)
except KeyboardInterrupt:
    GPIO.cleanup()