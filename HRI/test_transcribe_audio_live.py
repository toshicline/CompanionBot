import sys
import queue
import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel

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
BUFFER_SIZE_SECONDS = 5 # number of seconds of audio to parse at a time
TARGET_SAMPLES = SAMPLE_RATE * BUFFER_SIZE_SECONDS

# Thread-safe queue for incoming mic chunks
audio_queue = queue.Queue()

def audio_callback(indata,frames,time_info,status):
    """Called by sounddevice for every audio block from the mic
    
    Returns:
        None
    """

    if (status):
        print(status,file=sys.stderr)

    audio_queue.put(indata.copy().flatten())

# Init model
model = WhisperModel(MODEL_SIZE,device=DEVICE,compute_type=COMPUTE_TYPE)

print("Listening... Press Ctrl+C top stop")

# Configure microphone stream (1 channel, 16kHz)
try:
    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype=np.float32,
        callback=audio_callback
    ):
        buffer = np.array([],dtype=np.float32)

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
                    print(f"[Live] {segment.text}")

except KeyboardInterrupt:
    print("\nStopped listening.")