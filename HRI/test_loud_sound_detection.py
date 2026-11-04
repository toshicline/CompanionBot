import gpiod # type:ignore

CHIP_NAME = "gpiochip0"
LINE_OFFSET = 7  # PA.07

def main():
    print(f"Initializing gpiod on {CHIP_NAME}, line {LINE_OFFSET}...")
    
    chip = gpiod.Chip(CHIP_NAME)
    line = chip.get_line(LINE_OFFSET)
    line.request(consumer="ky038_detector", type=gpiod.LINE_REQ_DIR_IN)
    
    print("Monitoring for loud sounds (KY-038)... Press Ctrl+C to exit.")
    
    try:
        last_state = line.get_value()
        while True:
            current_state = line.get_value()
            
            # Print state changes to debug what the pin is actually seeing
            if current_state != last_state:
                print(f"Pin state changed: {last_state} -> {current_state}")
            
            # Catch either falling edge (1 -> 0) or rising edge (0 -> 1) depending on module pull
            if last_state == 1 and current_state == 0:
                print("\n🚨 Loud sound detected (Clap/Tap)! [gpiod trigger]")
                
            last_state = current_state
            
    except KeyboardInterrupt:
        print("\nExiting and releasing GPIO line...")
        line.release()
        chip.close()

if __name__ == "__main__":
    main()
