"""ATOM's web screen (v13): a full-window JARVIS-style display drawn in web/ by Edge WebView2.

The screen IS the assistant: an animated atom in the middle, and panels (chat, news, music,
inbox, reminders, markets, briefing) that fly in by voice or dock click. With panels open the
atom slides to the bottom-right corner.

WebApp mixes in Engine exactly like app.AtomApp does, and offers the same window methods
(set_status, set_level, add, after, show_window, hide_window, quit_app, mainloop...).
Python -> page: one sender thread calls window.evaluate_js("ATOM.recv([...])") with JSON,
mic level at most ~15 times a second. Page -> Python: pywebview js_api (the Api class below).
"""

import json
import os
import queue
import sys
import threading
import time
from collections import deque
from pathlib import Path

import ui_bridge
from engine import Engine

WEB = Path(__file__).with_name("web")
LEVEL_EVERY = 1 / 15      # seconds between mic-level updates sent to the page
BATCH_EVERY = 0.06        # how often queued messages are flushed to the page
DEBUG = os.getenv("ATOM_UI_DEBUG", "") == "1"


def state_for(text):
    """Status text from Engine -> one of the screen's states (same rules as app.py)."""
    lowered = (text or "").lower()
    if "listening" in lowered:
        return "listening"
    if "thinking" in lowered or "verifying" in lowered or "recogniz" in lowered or "working" in lowered:
        return "thinking"
    if "speaking" in lowered:
        return "speaking"
    if "locked" in lowered or "error" in lowered:
        return "locked"
    return "idle"


class Api:
    """Called from web/app.js as window.pywebview.api.<name>(...). Each call runs on its own thread.
    Only underscore attributes are kept here so pywebview doesn't expose the whole app."""

    def __init__(self, app):
        self._app = app

    def ready(self):
        return self._app.snapshot()

    def toggle(self, name):
        self._app.toggle_panel(str(name))
        return True

    def open_panels(self, names):
        self._app.show_panels(ui_bridge.expand(names), [])
        return True

    def close_panels(self, names):
        self._app.show_panels([], ui_bridge.expand(names))
        return True

    def live(self, on):
        self._app.set_live(bool(on))
        return True

    def talk(self):
        self._app.start()
        return True

    def stop(self):
        self._app.cancel_current()
        return True

    def media(self, action):
        self._app.media(str(action))
        return True

    def hide(self):
        self._app.hide_window()
        return True


def _check_backend(webview):
    """On Windows make sure Edge WebView2 is there; otherwise pywebview would fall back to old IE."""
    if sys.platform != "win32":
        return "auto"
    from webview.platforms import winforms
    if not getattr(winforms, "is_chromium", False):
        raise RuntimeError("Microsoft Edge WebView2 Runtime not found. Get it from "
                           "https://developer.microsoft.com/microsoft-edge/webview2/")
    return "edgechromium"


class WebApp(Engine):
    def __init__(self):
        import webview
        self._webview = webview
        self._gui = _check_backend(webview)
        self.busy = False
        self.cancel_event = threading.Event()
        self.wake_model = None
        self.state = "idle"
        self.status_text = "Starting"
        self.lines = deque(maxlen=40)
        self.panels = []
        self.briefing = False
        self.live = False
        self.data = {}
        self._panel_lock = threading.Lock()
        self._level = 0.0
        self._outbox = queue.Queue()
        self._wake_refresh = threading.Event()
        self._quitting = False
        self._close_handler = None
        self._started = False
        self.window = webview.create_window(
            "ATOM", url=str(WEB / "index.html"), js_api=Api(self), width=1280, height=720,
            resizable=True, min_size=(900, 560), background_color="#06090e")
        self.window.events.closing += self._on_closing
        threading.Thread(target=self._sender, daemon=True, name="ui-sender").start()

    # ---- What Engine and atom.py call ------------------------------------------------------

    def set_status(self, text):
        self.state = state_for(text)
        self.status_text = text
        self._send({"t": "status", "state": self.state, "text": text, "online": not getattr(self, "offline", False)})

    def set_level(self, level):
        try:
            self._level = max(self._level, float(level))
        except (TypeError, ValueError):
            pass

    def add(self, who, text):
        line = {"who": who, "text": str(text), "at": time.strftime("%H:%M")}
        self.lines.append(line)
        self._send({"t": "line", **line})

    def after(self, ms, fn):
        def run():
            try:
                fn()
            except Exception as error:
                print("UI task failed:", type(error).__name__, str(error)[:120])
        timer = threading.Timer(max(0, ms) / 1000.0, run)
        timer.daemon = True
        timer.start()
        return timer

    def show_window(self):
        try:
            self.window.show()
            self.window.restore()
            self.window.on_top = True
            self.after(600, lambda: setattr(self.window, "on_top", False))
        except Exception as error:
            print("Show window failed:", type(error).__name__)

    def hide_window(self):
        try:
            self.window.hide()
        except Exception as error:
            print("Hide window failed:", type(error).__name__)

    def quit_app(self):
        self._quitting = True
        try:
            self.window.destroy()
        except Exception:
            pass

    def close_to_tray(self):
        """Closing the window hides it (the tray icon brings it back)."""
        self._close_handler = self.hide_window

    # tkinter-style names, so older code keeps working
    def withdraw(self):
        self.hide_window()

    def deiconify(self):
        self.show_window()

    def destroy(self):
        self.quit_app()

    def protocol(self, name, handler=None):
        if name == "WM_DELETE_WINDOW":
            self._close_handler = handler

    def attributes(self, *args, **kwargs):
        return None

    def lift(self):
        return None

    def focus_force(self):
        return None

    def mainloop(self):
        """Blocks on the main thread until the window is destroyed."""
        self._started = True
        threading.Thread(target=self._refresher, daemon=True, name="ui-local").start()
        threading.Thread(target=self._net_refresher, daemon=True, name="ui-net").start()
        options = {"http_server": True, "debug": DEBUG}
        if self._gui != "auto":
            options["gui"] = self._gui
        self._webview.start(**options)

    # ---- Panels ----------------------------------------------------------------------------

    def show_panels(self, open=None, close=None, briefing=False):
        """open/close: canonical names from ui_bridge.expand(): panels, 'live' or 'all'."""
        with self._panel_lock:
            panels = list(self.panels)
            close = list(close or [])
            if "all" in close:
                panels, self.live, self.briefing = [], False, False
            for name in close:
                if name in panels:
                    panels.remove(name)
                if name in ("news", "live"):
                    self.live = False
            for name in open or []:
                if name == "all":
                    for each in ui_bridge.PANELS:
                        if each not in panels:
                            panels.append(each)
                    continue
                if name == "live":
                    self.live = True
                    name = "news"
                if name in ui_bridge.PANELS and name not in panels:
                    panels.append(name)
            if briefing:
                self.briefing = True
            elif not set(ui_bridge.BRIEFING) <= set(panels):
                self.briefing = False
            self.panels = panels
        self._push_panels()
        self._wake_refresh.set()

    def toggle_panel(self, name):
        if name == "core":
            self.show_panels([], ["all"])
        elif name == "briefing":
            self.show_panels(ui_bridge.BRIEFING, [], briefing=True)
        elif name in self.panels:
            self.show_panels([], [name])
        else:
            self.show_panels([name], [])

    def set_live(self, on):
        """Live video on (opens news) or off (news stays open)."""
        if on:
            self.show_panels(["live"], [])
        else:
            self.live = False
            self._push_panels()

    def _push_panels(self):
        import hud_feeds
        self._send({"t": "panels", "open": list(self.panels), "briefing": self.briefing,
                    "live": self.live, "channel": hud_feeds.channel()})

    def media(self, action):
        from tools import media_control
        try:
            media_control(action)
        except Exception as error:
            print("Media button failed:", type(error).__name__)
        self.after(700, self._wake_refresh.set)

    def snapshot(self):
        """Everything the page needs after (re)loading."""
        import hud_feeds
        return {"state": self.state, "status": self.status_text, "lines": list(self.lines)[-20:],
                "open": list(self.panels), "briefing": self.briefing, "live": self.live,
                "channel": hud_feeds.channel(), "data": dict(self.data),
                "online": not getattr(self, "offline", False)}

    # ---- Background work -------------------------------------------------------------------

    def _send(self, message):
        self._outbox.put(message)

    def _set_data(self, key, value):
        """Send a data block only when it changed."""
        if value is None or self.data.get(key) == value:
            return
        self.data[key] = value
        self._send({"t": "data", "key": key, "value": value})

    def _sender(self):
        last_level, last_level_at = -1.0, 0.0
        while not self._quitting:
            time.sleep(BATCH_EVERY)
            batch = []
            while True:
                try:
                    batch.append(self._outbox.get_nowait())
                except queue.Empty:
                    break
            now = time.time()
            if now - last_level_at >= LEVEL_EVERY:
                level, self._level = self._level, 0.0
                if abs(level - last_level) > 0.01:
                    batch.append({"t": "level", "v": round(level, 3)})
                    last_level, last_level_at = level, now
            if not batch or not self._started:
                if batch:  # window not running yet: keep them for later
                    for message in batch:
                        if message["t"] != "level":
                            self._outbox.put(message)
                    time.sleep(0.2)
                continue
            try:
                self.window.evaluate_js("window.ATOM && ATOM.recv(%s)" % json.dumps(batch, ensure_ascii=False))
            except Exception as error:
                if DEBUG:
                    print("Page update failed:", type(error).__name__, str(error)[:120])

    def _refresher(self):
        """Cheap local data every few seconds: reminders, inbox, battery, now playing."""
        import hud_feeds
        ticks = 0
        while not self._quitting:
            try:
                self._set_data("reminders", hud_feeds.reminders())
                self._set_data("inbox", hud_feeds.inbox())
                if ticks % 6 == 0:
                    self._set_data("battery", hud_feeds.battery())
                if "music" in self.panels:
                    self._set_data("music", hud_feeds.now_playing())
            except Exception as error:
                print("Screen refresh error:", type(error).__name__, str(error)[:120])
            ticks += 1
            self._wake_refresh.wait(3 if "music" in self.panels else 5)
            self._wake_refresh.clear()

    def _net_refresher(self):
        """Network data, all cached for 10+ minutes in hud_feeds, so this loop is cheap."""
        import hud_feeds
        while not self._quitting:
            try:
                self._set_data("ticker", hud_feeds.ticker())
                self._set_data("weather", hud_feeds.weather())
                if "news" in self.panels or not self.data.get("news"):
                    self._set_data("news", hud_feeds.news())
                if "markets" in self.panels:
                    self._set_data("fx", hud_feeds.fx_history())
            except Exception as error:
                print("Screen network error:", type(error).__name__, str(error)[:120])
            for _ in range(60):  # check again in a minute, sooner if a panel just opened
                if self._quitting or ("markets" in self.panels and "fx" not in self.data) or \
                        ("news" in self.panels and not self.data.get("news")):
                    break
                time.sleep(1)

    def _on_closing(self):
        if self._quitting or self._close_handler is None:
            self._quitting = True
            return True
        threading.Timer(0.05, self._close_handler).start()
        return False  # keep running in the tray
