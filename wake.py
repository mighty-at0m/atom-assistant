import os
import threading
import time
from pathlib import Path

import sounddevice as sd
from openwakeword.model import Model
from openwakeword.utils import download_models

RATE = 16000
CHUNK = 1280      # 80 ms of audio per check
# Measured "Hey Jarvis" scores were 0.36 to 0.79 with background noise under 0.03.
# Override with ATOM_WAKE_THRESHOLD (lower = easier to trigger, more false wakes).
THRESHOLD = float(os.getenv("ATOM_WAKE_THRESHOLD", "0.35"))


PAUSE = threading.Event()  # set while ATOM is in a conversation, so two listeners never share the model


def _wake_scores_score(scores):
    if not scores:
        return 0.0
    return float(max(scores.values()))


def load_model(model_name=None, model_path=None):
    candidates = []
    if model_path:
        candidates.append(Path(model_path).expanduser())
    env_path = os.getenv("ATOM_WAKE_MODEL_PATH")
    if env_path:
        candidates.append(Path(env_path).expanduser())
    default_paths = [
        Path(__file__).with_name("hey_at_tom.onnx"),
        Path(__file__).with_name("models") / "hey_atom.onnx",
    ]
    candidates.extend(default_paths)

    for candidate in candidates:
        if candidate.exists():
            path = candidate.resolve()
            return Model(wakeword_models=[str(path)], inference_framework="onnx" if path.suffix.lower() == ".onnx" else "tflite")

    model_name = model_name or os.getenv("ATOM_WAKE_MODEL", "hey_jarvis")
    if model_name.lower().endswith((".onnx", ".tflite")):
        return Model(wakeword_models=[model_name], inference_framework="onnx" if model_name.lower().endswith(".onnx") else "tflite")
    download_models(model_names=[model_name])  # first run downloads a few small files
    return Model(wakeword_models=[model_name], inference_framework="onnx")


def wait_for_wake(model):
    """Blocks until the wake word is heard, then returns the score."""
    while True:
        try:
            with sd.InputStream(samplerate=RATE, channels=1, dtype="int16", blocksize=CHUNK) as stream:
                while True:
                    frame, _ = stream.read(CHUNK)
                    if PAUSE.is_set():
                        continue
                    scores = model.predict(frame.flatten())
                    score = _wake_scores_score(scores)
                    if score > THRESHOLD:
                        model.reset()
                        return score
        except sd.PortAudioError as error:
            # Reopen the microphone after another audio stream releases it.
            # This prevents a one-off handoff failure from killing ATOM's wake loop.
            print("Wake microphone reset:", error)
            model.reset()
            time.sleep(0.25)


def wake_during(model, stop_event):
    """Listen for the wake word until stop_event is set. True if it was heard (used to interrupt speech)."""
    model.reset()
    try:
        with sd.InputStream(samplerate=RATE, channels=1, dtype="int16", blocksize=CHUNK) as stream:
            while not stop_event.is_set():
                frame, _ = stream.read(CHUNK)
                scores = model.predict(frame.flatten())
                if _wake_scores_score(scores) > THRESHOLD:
                    model.reset()
                    return True
    except sd.PortAudioError:
        pass
    return False
