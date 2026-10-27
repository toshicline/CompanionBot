import sys
import queue
import wave
import time
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



def ding(path="tmp/tone.wav"):
    """Play a tone that indicates the mic is hot
    
    Returns:
        None
    """
    time.sleep(.5)
    with wave.open(path, 'rb') as wf:
        samplerate =wf.getframerate()
        frames = wf.readframes(wf.getnframes())
        
        # Directly parse as 16-bit signed integer and normalize
        audio_data = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
            
        # Play the audio through the default output device
        sd.play(audio_data, samplerate)
        sd.wait()

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
            return idx
    print("Anker PowerConf input not found!")
    return None

def listen(max_wait_seconds=10, silence_pause_seconds=3):
    """Listen until speech is detected, then continue until the user stops speaking.

    Args:
        max_wait_seconds (int): Max time to wait for speech to begin.
        silence_pause_seconds (float): Seconds of silence to wait before concluding speech is done.

    Returns:
        str: Combined transcript of what the user said.
    """
    # Clear out any leftover stale audio in the queue
    while not audio_queue.empty():
        try:
            audio_queue.get_nowait()
        except queue.Empty:
            break

    transcripts = []
    ding()

    with sd.InputStream(
        device=AUDIO_DEVICE_ID,
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype=np.float32,
        callback=audio_callback
    ):
        buffer = np.array([], dtype=np.float32)
        total_offset_seconds = 0.0
        session_start_time = datetime.now()
        
        speech_detected = False
        last_speech_time = datetime.now()

        while True:
            current_time = datetime.now()
            
            # Phase 1: If speech hasn't started yet, check max wait timeout
            if not speech_detected:
                elapsed_wait = (current_time - session_start_time).total_seconds()
                if elapsed_wait > max_wait_seconds:
                    print("No speech detected (timeout).")
                    break
            else:
                # Phase 2: Speech has started. Check if user has stopped talking for long enough
                silence_duration = (current_time - last_speech_time).total_seconds()
                if silence_duration > silence_pause_seconds:
                    break

            try:
                # Wait up to 0.1 seconds for the next audio chunk
                chunk = audio_queue.get(timeout=0.1)
                buffer = np.append(buffer, chunk)
            except queue.Empty:
                continue

            # Process once we hit our target buffer size
            if len(buffer) >= TARGET_SAMPLES:
                audio_chunk = buffer[:TARGET_SAMPLES]
                buffer = buffer[TARGET_SAMPLES:]

                segments, info = model.transcribe(
                    audio_chunk,
                    beam_size=BEAM_SIZE,
                    language="en",
                    vad_filter=True,
                )

                chunk_has_speech = False
                for segment in segments:
                    cleaned_text = segment.text.strip()
                    if cleaned_text:
                        chunk_has_speech = True
                        transcripts.append(cleaned_text)

                if chunk_has_speech:
                    speech_detected = True
                    last_speech_time = datetime.now()  # Reset silence timer when speech is found

                total_offset_seconds += BUFFER_SIZE_SECONDS

    return " ".join(transcripts).strip()



# Init model
model = WhisperModel(MODEL_SIZE,device=DEVICE,compute_type=COMPUTE_TYPE)

# Thread-safe queue for incoming mic chunks
audio_queue = queue.Queue()

# Set the audio device, or raise an error if it does not exist
AUDIO_DEVICE_ID = get_anker_input_device_id()
if AUDIO_DEVICE_ID == None:
    raise Exception("Could not detect external mic. Ensure that it is connected via USB.")


if __name__ == "__main__":
    phrase = listen()
    print(f"phrase: {phrase}")