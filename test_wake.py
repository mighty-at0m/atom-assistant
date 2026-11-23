"""Say your wake word and watch the score. Use: python test_wake.py  (Hey Atom and Hey Jarvis; 1.00 = heard)
Optional: python test_wake.py some_model.onnx to test an openWakeWord model on its own.
The bar shows the best score each second. ATOM wakes above THRESHOLD (default 0.35)."""

import sys
import time

import sounddevice as sd
from openwakeword.model import Model
from openwakeword.utils import download_models

from wake import CHUNK, RATE, THRESHOLD, load_model

if len(sys.argv) > 1:
    download_models(model_names=["hey_jarvis"])
    model = Model(wakeword_models=[sys.argv[1]], inference_framework="onnx")
else:
    model = load_model()
print("Model:", ", ".join(model.models.keys()), "| wakes above", THRESHOLD)
print("Say your wake word a few times, normally, softly, from across the room. Ctrl+C to stop.")

best, started = 0.0, time.time()
with sd.InputStream(samplerate=RATE, channels=1, dtype="int16", blocksize=CHUNK) as stream:
    while True:
        frame, _ = stream.read(CHUNK)
        best = max(best, float(max(model.predict(frame.flatten()).values())))
        if time.time() - started >= 1.0:
            mark = "  <-- WAKE" if best > THRESHOLD else ""
            print(f"{best:4.2f} " + "#" * int(best * 40) + mark)
            best, started = 0.0, time.time()
