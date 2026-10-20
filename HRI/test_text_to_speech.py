import subprocess
import sounddevice as sd
import numpy as np

# Samples for voices are available at: https://rhasspy.github.io/piper-samples/
PIPER_MODEL_PATH = "models/en_US-hfc_female-medium.onnx"

def speak(text, model_path=PIPER_MODEL_PATH):
    # Open Piper stream
    proc = subprocess.Popen(
        ["piper", "--model", model_path, "--output-raw"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE
    )
    
    # Write text into the stream
    proc.stdin.write(text.encode("utf-8"))
    proc.stdin.close()
    print(f"Robot> {text}\n")
    
    # Read and speak simultaneously
    sample_rate = 22050
    with sd.OutputStream(samplerate=sample_rate, channels=1, dtype='int16') as stream:
        while True:
            # Read chunks of raw audio data
            raw_chunk = proc.stdout.read(4096)
            if not raw_chunk:
                break
            # Convert bytes to a numpy array of 16-bit integers
            audio_data = np.frombuffer(raw_chunk, dtype=np.int16)
            stream.write(audio_data)
            
    proc.wait()

if __name__ == "__main__":
    speak("Howdy World!")
