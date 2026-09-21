from faster_whisper import WhisperModel

MODEL_SIZE = "base.en"
DEVICE = "cuda"
COMPUTE_TYPE = "int8_float16"

model = WhisperModel(MODEL_SIZE,device=DEVICE,compute_type=COMPUTE_TYPE)    