import sounddevice as sd

def get_anker_input_device_id():
    devices = sd.query_devices()
    for idx, device in enumerate(devices):
        # Look for PowerConf and ensure it has input channels (1 in, 0 out)
        if "powerconf" in device['name'].lower() and device['max_input_channels'] > 0:
            print(f"Found Anker microphone at index {idx}: {device['name']}")
            return idx
    print("Anker PowerConf input not found! Falling back to default.")
    return None

print(sd.query_devices())

print()

get_anker_input_device_id()