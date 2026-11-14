import numpy as np

from stt import record
from voicelock import load_encoder, embed, VOICE_FILE

print("Loading voice model (first run downloads about 80 MB)...")
enc = load_encoder()

lines = [
    "Hey Jarvis, what's the weather like today?",
    "Open VS Code and start a new Python project.",
    "My name is Atom and I make AI tutorials.",
    "Tell me something fun about space.",
    "What's my laptop's battery level right now?",
    "Please read my schedule and remind me about the meeting.",
    "Set a quick note for my next idea and summarize it.",
    "I want you to help me debug this Python script.",
    "Turn on the lights in the living room and tell me the time.",
    "Say a short greeting and then start a timer for ten minutes.",
]

samples = []
for i, line in enumerate(lines, 1):
    input(f"[{i}/{len(lines)}] Press Enter, then read: {line}")
    samples.append(embed(enc, record(5)))

mine = np.mean(samples, axis=0)
mine = mine / np.linalg.norm(mine)
np.save(VOICE_FILE, mine)
print("Saved your voice to", VOICE_FILE)