import Jetson.GPIO as GPIO
import time

# Define the physical board pin connected to the KY-038 DO pin
DO_PIN = 18  

def setup_sensor():
    # Set up the GPIO board mode
    GPIO.setmode(GPIO.BOARD)
    # Configure the pin as an input
    GPIO.setup(DO_PIN, GPIO.IN)

def sound_triggered_callback(channel):
    print("\n Loud sound detected!")

    # TODO: React to this somehow

def main():
    setup_sensor()
    
    GPIO.add_event_detect(
        DO_PIN, 
        GPIO.FALLING, 
        callback=sound_triggered_callback, 
        bouncetime=300 # Prevents multiple triggers from a single sound echo
    )
    
    print("Monitoring for loud sounds... Press Ctrl+C to exit.")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nCleaning up GPIO...")
        GPIO.cleanup()

if __name__ == "__main__":
    main()
