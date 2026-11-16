import os
import sys

from wake import load_model, wait_for_wake

model_path = sys.argv[1] if len(sys.argv) > 1 else os.getenv("ATOM_WAKE_MODEL_PATH", "models/hey_atom.onnx")
model = load_model(model_path=model_path)
print(f"Using wake model: {model_path}")
print("Say 'hey atom'... (Ctrl+C to stop)")
while True:
    score = wait_for_wake(model)
    print(f"Wake word heard! score {score:.2f}")