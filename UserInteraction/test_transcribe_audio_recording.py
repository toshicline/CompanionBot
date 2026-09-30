import sys
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

# Take audio file as input
try:
    file = sys.argv[1]
except IndexError:
    print("No audio file specified!")
    exit()

model = WhisperModel(MODEL_SIZE,device=DEVICE,compute_type=COMPUTE_TYPE)

segments, info = model.transcribe(file,beam_size=BEAM_SIZE)

print(f"Language: {info.language} ({info.language_probability*100}%)")

for segment in segments:
    print(f"[{segment.start:.0f}s -> {segment.end:.0f}s] {segment.text}")