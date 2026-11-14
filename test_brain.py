# Text-only test of the brain and tools. No microphone or speaker needed.
import time

from fastbrain import ask

questions = [
    "What's my battery level?",
    "What time is it?",
    "How do I open a bank account?",
    "Open notepad",
    "Take a screenshot",
    "Open Chrome",
    "Open Microsoft Edge",
    "Search YouTube for lofi music",
    "Play a song by Dave",
    "Pause the music",
    "Close notepad",
    "no",
]
for question in questions:
    started = time.time()
    print("You:", question)
    print("ATOM:", ask(question), "(" + str(round(time.time() - started, 1)) + "s)")
    print()
