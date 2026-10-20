import sounddevice as sd
import numpy as np
import os

SAMPLE_RATE = 16000 # Audio sample rate at 16kHz
BLOCK_SIZE = 1024 # Number of frames per buffer block
CHANNELS = 1
LOUD_SOUND_THRESHOLD_DBFS = -5 # Loud sound threshold in dBFS
TERMINAL_WIDTH = os.get_terminal_size().columns

def print_flush(text):
    """Print on the same line as before (useful for many repetitive prints of location/range)
    
    Args:
        text: the text to print

    Returns:
        None
    """

    print(f"\r\033[K{text}", end="", flush=True)

def get_anker_input_device_id():
    """Detect what index the anker microphone is at
    
    Returns:
        int: index of anker powerconf (or None)
    """

    devices = sd.query_devices()
    for idx, device in enumerate(devices):
        # Look for PowerConf and ensure it has input channels (1 in, 0 out)
        if "powerconf" in device['name'].lower() and device['max_input_channels'] > 0:
            print(f"Found Anker microphone at index {idx}: {device['name']}\n")
            return idx
    print("Anker PowerConf input not found!")
    return None

def audio_callback(indata,frames,time,status):

    # Handle errors
    if status:
        print(f"Warning: {status}",flush=True)

    # Calcuate RMS of audio chunk
    volume_rms = np.sqrt(np.mean(indata**2))
    volume_rms = max(volume_rms,1e-9) # make sure RMS is not 0 for dB calculation

    # Calculate volume in dBFS
    dBFS = 20 * np.log10(volume_rms)

    draw_ascii_meter(dBFS)

def draw_ascii_meter(dbfs_val, min_dbfs=-50, max_dbfs=0):

    bar_length = TERMINAL_WIDTH - 14

    # Clamp the incoming dBFS value between our display min and max bounds
    clamped_val = max(min(dbfs_val,max_dbfs), min_dbfs)

    # Normalize dBFS range (min_db to max_db) into a 0.0 to 1.0 scale for the bar length
    normalized = (clamped_val - min_dbfs) / (max_dbfs - min_dbfs)
    normalized_threshold = (LOUD_SOUND_THRESHOLD_DBFS - min_dbfs) / (max_dbfs - min_dbfs)

    n_filled_blocks = int(bar_length*normalized)
    threshold_block_index = int(bar_length*normalized_threshold)
    bar_fill = ""
    for i in range(n_filled_blocks):
        bar_fill += "*"
    for i in range(bar_length-n_filled_blocks):
        bar_fill += " "

    bar_fill = list(bar_fill)
    bar_fill[threshold_block_index] = "\033[37m|\033[31m"
    bar_fill = "".join(bar_fill)

    print(f"\r\033[K[\033[32m{bar_fill}\033[37m] {clamped_val:05.1f} dBFS", end="", flush=True)


def listen(device_id=None):
    try:
        with sd.InputStream(
            device=device_id,
            channels=CHANNELS,
            samplerate=SAMPLE_RATE,
            blocksize=BLOCK_SIZE,
            callback=audio_callback
        ):
            print("Listening started...")
            while True:
                sd.sleep(1000) # Run infinitely
    except KeyboardInterrupt:
        print("\nStopped listening.")
    except Exception as e:
        print(f"Error opening audio stream: {e}")

listen(device_id=get_anker_input_device_id())