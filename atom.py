import os
import sys
HERE = os.path.dirname(os.path.abspath(sys.argv[0]))
os.chdir(HERE)  # works from the desktop shortcut or any other folder
if sys.stdout is None:  # pythonw has no console, so log to a file
    sys.stdout = sys.stderr = open(os.path.join(HERE, "atom.log"), "a", buffering=1, encoding="utf-8")
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

import ui_bridge
from wake import load_model, wait_for_wake

# ATOM_UI=web (default): the full-window v13 screen (pywebview + Edge WebView2).
# ATOM_UI=classic: the v12 CustomTkinter HUD. Web falls back to classic if it can't start.
UI_CHOICE = os.getenv("ATOM_UI", "web").strip().lower()


def classic_app():
    from app import AtomApp
    return AtomApp()


def make_app():
    if UI_CHOICE != "classic":
        try:
            from ui_web import WebApp
            return WebApp()
        except Exception as error:
            print("Web UI unavailable, using the classic window:", type(error).__name__, str(error)[:200])
    return classic_app()


app = make_app()
ui_bridge.set_ui(app)


def beep():
    try:
        winsound.Beep(880, 200)
    except Exception:
        pass
    # plays through the normal speakers too
    winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS | winsound.SND_ASYNC)


def show_window():
    app.show_window()


def wake_loop():
    try:
        print("Loading wake model...")
        app.set_status("Loading wake word...")
        model = load_model()
        import voicelock
        voicelock.ENC = voicelock.load_encoder()
        app.wake_model = model  # lets "hey atom" interrupt ATOM while it speaks
        print("Voice lock loaded")
        app.start_services()  # reminders, notifications, Telegram
        print("Ready. Say 'hey atom'")
        app.set_status("Standing by")
        while True:
            score = wait_for_wake(model)
            print(time.strftime("%H:%M:%S"), "Heard hey atom, score", round(float(score), 2))
            if not app.claim():
                print("Busy, ignoring")
            else:
                app.cancel_event.clear()
                app.after(0, show_window)
                beep()
                print("Listening for your request...")
                app.run_turn()
                print("Turn finished")
                app.set_status("Standing by")
            time.sleep(1.0)
            model.reset()
    except Exception:
        traceback.print_exc()
        app.set_status("Error: wake word crashed")


TRAY = {"icon": None}


def start_tray():
    """Tray icon by the clock: closing the window hides ATOM there instead of quitting."""
    try:
        import pystray
        from PIL import Image, ImageDraw
    except ImportError:
        return
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((4, 4, 60, 60), fill=(0, 60, 80, 255))
    draw.ellipse((14, 14, 50, 50), fill=(0, 229, 255, 255))
    draw.ellipse((24, 24, 40, 40), fill=(220, 255, 255, 255))

    def quit_atom(icon, item):
        icon.stop()
        app.after(0, app.quit_app)
    menu = pystray.Menu(pystray.MenuItem("Show ATOM", lambda icon, item: app.after(0, show_window), default=True),
                        pystray.MenuItem("Hide", lambda icon, item: app.after(0, app.hide_window)),
                        pystray.MenuItem("Quit ATOM", quit_atom))
    TRAY["icon"] = pystray.Icon("ATOM", image, "ATOM", menu)
    TRAY["icon"].run_detached()
    app.close_to_tray()


start_tray()
threading.Thread(target=wake_loop, daemon=True).start()
try:
    app.mainloop()
except Exception:
    # The web window failed to open (e.g. WebView2 broke): carry on with the classic window.
    traceback.print_exc()
    if UI_CHOICE == "classic" or not hasattr(app, "show_panels"):
        raise
    print("Web UI crashed on start, switching to the classic window.")
    old = app
    app = classic_app()
    app.wake_model = old.wake_model  # the wake loop picks up the new window by itself
    ui_bridge.set_ui(app)
    if TRAY["icon"] is not None:
        app.close_to_tray()
    app.mainloop()
if TRAY["icon"] is not None:
    try:
        TRAY["icon"].stop()
    except Exception:
        pass
