import json
import os
import threading
import time
import types
import urllib.request
import zipfile

import sounddevice as sd
from openwakeword.model import Model
from openwakeword.utils import download_models

RATE = 16000
CHUNK = 1280      # 80 ms of audio per check
# Measured "Hey Jarvis" scores were 0.36 to 0.79 with background noise under 0.03.
# Override with ATOM_WAKE_THRESHOLD (lower = easier to trigger, more false wakes).
THRESHOLD = float(os.getenv("ATOM_WAKE_THRESHOLD", "0.35"))


PAUSE = threading.Event()  # set while ATOM is in a conversation, so two listeners never share the model


HERE = os.path.dirname(os.path.abspath(__file__))
# "Hey Atom" is heard by a small offline speech model (Vosk) that only listens for these phrases,
# so it works with any accent. "Hey Jarvis" keeps working as a backup.
# ATOM_WAKE_ENGINE: both (default), vosk, or oww (old openWakeWord only).
ENGINE = os.getenv("ATOM_WAKE_ENGINE", "both").lower()
PHRASES = [p.strip() for p in os.getenv("ATOM_WAKE_PHRASES", "hey atom,hi atom,hey adam").split(",") if p.strip()]
VOSK_NAME = "vosk-model-small-en-us-0.15"
VOSK_URL = "https://alphacephei.com/vosk/models/" + VOSK_NAME + ".zip"


def _oww_model():
    download_models(model_names=["hey_jarvis"])  # first run downloads a few small files
    custom = os.path.join(HERE, "models", "hey_atom.onnx")
    if ENGINE == "oww" and os.path.exists(custom):  # old trained model, only in oww mode
        return Model(wakeword_models=[custom], inference_framework="onnx")
    return Model(wakeword_models=["hey_jarvis"], inference_framework="onnx")


def _vosk_recognizer():
    from vosk import KaldiRecognizer, Model as VoskModel, SetLogLevel
    SetLogLevel(-1)
    folder = os.path.join(HERE, "models", VOSK_NAME)
    if not os.path.isdir(folder):
        print("Downloading the Hey Atom speech model (about 40 MB, one time)...")
        os.makedirs(os.path.join(HERE, "models"), exist_ok=True)
        zip_path = folder + ".zip"
        urllib.request.urlretrieve(VOSK_URL, zip_path)
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(os.path.join(HERE, "models"))
        os.remove(zip_path)
    grammar = json.dumps(PHRASES + ["[unk]"])
    return KaldiRecognizer(VoskModel(folder), RATE, grammar)


def load_model():
    """Returns an object with predict(frame) -> {name: score} and reset(), whatever engine is used."""
    oww = _oww_model() if ENGINE in ("both", "oww") else None
    rec = None
    if ENGINE in ("both", "vosk"):
        try:
            rec = _vosk_recognizer()
        except Exception as error:  # vosk missing or download failed: fall back to Hey Jarvis
            print("Hey Atom (Vosk) unavailable, using Hey Jarvis only:", error)
            if oww is None:
                oww = _oww_model()

    def predict(frame):
        scores = {}
        if oww is not None:
            scores.update(oww.predict(frame))
        if rec is not None:
            hit = 0.0
            if rec.AcceptWaveform(frame.tobytes()):
                text = json.loads(rec.Result()).get("text", "")
                if any(p in text for p in PHRASES):
                    hit = 1.0
            scores["hey_atom"] = hit
        return scores

    def reset():
        if oww is not None:
            oww.reset()
        if rec is not None:
            rec.Reset()

    names = ([] if oww is None else list(oww.models.keys())) + ([] if rec is None else ["hey_atom (vosk)"])
    print("Using wake words:", ", ".join(names))
    return types.SimpleNamespace(predict=predict, reset=reset, models=dict.fromkeys(names))


def wait_for_wake(model):
    """Blocks until Hey Atom or Hey Jarvis is heard, then returns the score."""
    while True:
        try:
            paused = False
            with sd.InputStream(samplerate=RATE, channels=1, dtype="int16", blocksize=CHUNK) as stream:
                while True:
                    frame, _ = stream.read(CHUNK)
                    if PAUSE.is_set():
                        paused = True
                        continue
                    if paused:  # drop half-heard audio from before the conversation
                        model.reset()
                        paused = False
                    scores = model.predict(frame.flatten())
                    score = float(max(scores.values()))
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
                if float(max(scores.values())) > THRESHOLD:
                    model.reset()
                    return True
    except sd.PortAudioError:
        pass
    return False
