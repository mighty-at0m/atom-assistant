import sounddevice as sd
import time
from openwakeword.model import Model
from openwakeword.utils import download_models

RATE = 16000
CHUNK = 1280      # 80 ms of audio per check
# Your measured wake phrase reached 0.36 while background noise stayed below
# 0.03. 0.30 gives it useful headroom without making false activations likely.
THRESHOLD = 0.40


def load_model():
    download_models(model_names=["hey_jarvis"])  # first run downloads a few small files
    return Model(wakeword_models=["hey_jarvis"], inference_framework="onnx")


def wait_for_wake(model):
    """Blocks until 'Hey Jarvis' is heard, then returns the score."""
    while True:
        try:
            with sd.InputStream(samplerate=RATE, channels=1, dtype="int16", blocksize=CHUNK) as stream:
                while True:
                    frame, _ = stream.read(CHUNK)
                    scores = model.predict(frame.flatten())
                    score = float(scores.get("hey_jarvis", max(scores.values())))
                    if score > THRESHOLD:
                        model.reset()
                        return score
        except sd.PortAudioError as error:
            # Reopen the microphone after another audio stream releases it.
            # This prevents a one-off handoff failure from killing ATOM's wake loop.
            print("Wake microphone reset:", error)
            model.reset()
            time.sleep(0.25)
