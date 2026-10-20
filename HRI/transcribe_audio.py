import sys
import queue
import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel
from datetime import datetime,timedelta

MODEL_SIZE = "base.en"

# MacOS: cpu
# Jetson: cuda
DEVICE = "cpu"

# MacOS: int8
# Jetson: float16
COMPUTE_TYPE = "int8"

# Higher beam size = better speech processing (slower)
BEAM_SIZE = 5

SAMPLE_RATE = 16000 # faster-whisper requires 16kHz audio
BUFFER_SIZE_SECONDS = 3 # number of seconds of audio to parse at a time
TARGET_SAMPLES = SAMPLE_RATE * BUFFER_SIZE_SECONDS





def audio_callback(indata,frames,time_info,status):
    """Called by sounddevice for every audio block from the mic
    
    Returns:
        None
    """

    if (status):
        print(status,file=sys.stderr)

    audio_queue.put(indata.copy().flatten())

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





# Init model
model = WhisperModel(MODEL_SIZE,device=DEVICE,compute_type=COMPUTE_TYPE)

# Thread-safe queue for incoming mic chunks
audio_queue = queue.Queue()

# Set the audio device, or raise an error if it does not exist
AUDIO_DEVICE_ID = get_anker_input_device_id()
if AUDIO_DEVICE_ID == None:
    raise Exception("Could not detect external mic. Ensure that it is connected via USB.")

print("Listening... Press Ctrl+C to stop")

# Configure microphone stream (1 channel, 16kHz)
try:
    with sd.InputStream(
        device=AUDIO_DEVICE_ID,
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype=np.float32,
        callback=audio_callback
    ):
        buffer = np.array([],dtype=np.float32)

        # Initiate time tracking variables
        total_offset_seconds = 0.0
        session_start_time = datetime.now()

        while True:
            try:
                # Wait up to 0.1 seconds for the next audio chunk from the queue
                chunk = audio_queue.get(timeout=0.1)
                buffer = np.append(buffer, chunk)
            except queue.Empty:
                # Timeout occurred, loop back to check again
                pass

            # Process once we hit our target buffer size
            if len(buffer) >= TARGET_SAMPLES:
                audio_chunk = buffer[:TARGET_SAMPLES]
                # Keep any leftover samples for the next buffer to prevent audio clipping
                buffer = buffer[TARGET_SAMPLES:]

                segments, info = model.transcribe(
                    audio_chunk,
                    beam_size=BEAM_SIZE,
                    language="en",
                    vad_filter=True,
                )

                for segment in segments:

                    # Absolute elapsed seconds since start of program
                    time_abs_start = segment.start + total_offset_seconds

                    # Map elapsed seconds to real-world time
                    segment_datetime = session_start_time + timedelta(seconds=time_abs_start)

                    print(f"[{segment_datetime.strftime("%Y-%m-%d %H:%M:%S")}] {segment.text}")

                # Advance time by the duration of the chunk that was just processed
                total_offset_seconds += BUFFER_SIZE_SECONDS

except KeyboardInterrupt:
    print("\nStopped listening.")