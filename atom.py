import sys
if sys.stdout is None:  # pythonw has no console, so log to a file
    sys.stdout = sys.stderr = open("atom.log", "a", buffering=1)
import socket
LOCK = socket.socket()
try:
    LOCK.bind(("127.0.0.1", 47821))  # only one ATOM at a time
except OSError:
    sys.exit(0)

import threading
import time
import traceback
import winsound

from app import AtomApp
from wake import load_model, wait_for_wake

app = AtomApp()


def beep():
    try:
        winsound.Beep(880, 200)
    except Exception:
        pass
    # plays through the normal speakers too
    winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS | winsound.SND_ASYNC)


def show_window():
    app.deiconify()
    app.lift()
    app.attributes("-topmost", True)
    app.after(500, lambda: app.attributes("-topmost", False))
    app.focus_force()


def wake_loop():
    try:
        print("Loading wake model...")
        app.set_status("Loading wake word...")
        model = load_model()
        import voicelock
        voicelock.ENC = voicelock.load_encoder()
        print("Voice lock loaded")
        print("Ready. Say 'Hey Jarvis'")
        app.set_status("Say 'Hey Jarvis' or click the mic")
        while True:
            score = wait_for_wake(model)
            print("Heard Hey Jarvis, score", round(float(score), 2))
            if app.busy:
                print("Busy, ignoring")
            else:
                app.busy = True
                app.after(0, lambda: app.mic.configure(fg_color="#c0392b"))
                app.after(0, show_window)
                beep()
                print("Listening for your request...")
                app.run_turn()
                print("Turn finished")
                app.set_status("Say 'Hey Jarvis' or click the mic")
            time.sleep(1.0)
            model.reset()
    except Exception:
        traceback.print_exc()
        app.set_status("Wake word crashed - see console")


threading.Thread(target=wake_loop, daemon=True).start()
app.mainloop()
