"""ATOM's brain-to-voice engine, separate from the window so any interface can use it.

A window class mixes in Engine and provides: set_status(text), set_level(level), add(who, text),
after(ms, fn), and optionally show_window(). Engine handles conversation mode, barge-in, offline mode,
reminders, notifications, Telegram and do-not-disturb.
"""

import os
import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from stt import listen_for_barge_in, record_until_silence, to_wav_bytes, transcribe
from fastbrain import ask
from tts import speak_async, stop_speaking
from voicelock import check

# Conversation mode: after the wake word, keep talking with no wake word until you go quiet
# for this long (seconds). Then ATOM goes back to standby and needs "hey atom" again.
IDLE_SECONDS = float(os.getenv("ATOM_IDLE_SECONDS", "120"))
SLEEP_WORDS = {"stop", "cancel", "never mind", "go to sleep", "sleep", "goodbye", "bye", "that's all",
               "that is all", "standby", "stand by", "go to standby", "thank you", "thanks"}
# Whisper sometimes "hears" these in background noise; ignore them instead of answering.
NOISE_TEXT = {"", "thanks for watching", "you", "thank you for watching"}


_claim_lock = threading.Lock()


class Engine:
    busy = False
    wake_model = None
    offline = False

    def claim(self):
        """Mark ATOM busy if it is free. True if this caller got it."""
        with _claim_lock:
            if self.busy:
                return False
            self.busy = True
            return True

    def start_services(self):
        """Reminders, notifications and Telegram. Call once after the window exists."""
        self.cancel_event = getattr(self, "cancel_event", None) or threading.Event()
        self.announcements = queue.Queue()
        # Each service starts on its own: one failing (say Telegram) must not stop the rest.
        try:
            import reminders
            reminders.watch(lambda text: self._queue("reminder", text))
        except Exception as error:
            print("Reminders unavailable:", type(error).__name__, str(error)[:120])
        try:
            import notifications
            notifications.watch(lambda note: self._queue("message", notifications.spoken(note), note))
        except Exception as error:
            print("Notifications unavailable:", type(error).__name__, str(error)[:120])
        try:
            import telegram_bot
            telegram_bot.start()
        except Exception as error:
            print("Telegram unavailable:", type(error).__name__, str(error)[:120])
        threading.Thread(target=self._announcer, daemon=True).start()

    def _release(self):
        """End-of-turn cleanup. Every step is guarded on its own, so one failure (say the
        wake model reset) can never leave ATOM busy or the wake word paused forever."""
        import ducker
        from wake import PAUSE
        try:
            ducker.restore()
        except Exception as error:
            print("Release: audio restore failed:", type(error).__name__)
        try:
            PAUSE.clear()
        except Exception as error:
            print("Release: wake unpause failed:", type(error).__name__)
        if self.wake_model is not None:
            try:
                self.wake_model.reset()
            except Exception as error:
                print("Release: wake reset failed:", type(error).__name__)
        self.busy = False

    def _queue(self, kind, text, note=None):
        import routines
        import telegram_bot
        telegram_bot.forward(kind, text)
        if kind == "message" and routines.DND["on"]:
            print("DND: kept for later:", text[:80])
            return
        self.announcements.put((kind, text))

    def _announcer(self):
        """Speak reminders and messages when ATOM is free, then listen for your answer."""
        while True:
            kind, text = self.announcements.get()
            while not self.claim():
                time.sleep(0.5)
            self.cancel_event.clear()
            if hasattr(self, "show_window"):
                self.after(0, self.show_window)
            self.run_turn(intro=text)

    def start(self):
        if not self.claim():
            return
        self.cancel_event.clear()
        threading.Thread(target=self.run_turn, daemon=True).start()

    def cancel_current(self):
        self.cancel_event.set()
        stop_speaking()
        self.set_status("Stopped")

    def _hear(self, audio):
        """Voice-check and transcribe at the same time. Returns (ok, score, text)."""
        with ThreadPoolExecutor(max_workers=2) as executor:
            voice = executor.submit(check, audio)
            text = executor.submit(transcribe, to_wav_bytes(audio))
            ok, score = voice.result()
            try:
                heard = text.result()
                self.offline = False
            except Exception as error:
                print("Online speech failed, using offline:", type(error).__name__)
                import offline
                heard = offline.transcribe_offline(audio.reshape(-1))
                self.offline = True
            return ok, score, heard

    def _think(self, heard):
        """Ask the brain, but if the user starts talking again, add their words and re-ask."""
        while True:
            self.set_status("Thinking...")
            done = threading.Event()
            extra = {}

            def watch():
                extra["audio"] = listen_for_barge_in(done, on_level=self.set_level)

            watcher = threading.Thread(target=watch, daemon=True)
            watcher.start()
            started = time.time()
            reply = ask(heard, should_stop=lambda: "audio" in extra and extra["audio"] is not None)
            print("Brain took", round(time.time() - started, 1), "seconds")
            done.set()
            watcher.join(timeout=30)
            audio = extra.get("audio")
            if audio is None or self.cancel_event.is_set():
                return reply
            self.set_status("Listening... adding that")
            ok, score, more = self._hear(audio)
            if not ok or not more:
                return reply
            heard = heard + " " + more
            self.add("You", heard)

    def _say(self, reply):
        """Speak; saying 'hey atom' or pressing Stop cuts it off. True if interrupted."""
        self.set_status("Speaking...")
        speaker = speak_async(reply)
        if self.wake_model is not None:
            finished = threading.Event()
            threading.Thread(target=lambda: (speaker.join(), finished.set()), daemon=True).start()
            from wake import wake_during
            interrupted = wake_during(self.wake_model, finished)
            if interrupted:
                stop_speaking()
                speaker.join(timeout=3)
                return True
        while speaker.is_alive():
            if self.cancel_event.is_set():
                stop_speaking()
                return True
            speaker.join(timeout=0.1)
        return False

    def run_turn(self, intro=None):
        from wake import PAUSE
        import ducker
        PAUSE.set()
        ducker.duck()  # music down while we talk
        try:
            if intro:
                self.add("ATOM", intro)
                self._say(intro)
            last_talk = time.time()
            first = True
            first_wait = 8 if intro else 7
            while not self.cancel_event.is_set():
                left = IDLE_SECONDS - (time.time() - last_talk)
                if left <= 0:
                    break  # quiet for too long: back to standby
                self.set_status("Listening..." if first else "Listening... go ahead")
                audio = record_until_silence(self.cancel_event, on_status=None, on_level=self.set_level,
                                             wait_for_speech_seconds=min(left, first_wait if first else left))
                if audio is None:
                    if first:
                        break
                    continue  # nobody spoke yet; keep waiting until the idle time runs out
                self.set_status("Recognizing...")
                ok, score, heard = self._hear(audio)
                print("Voice lock score", round(score, 2), "| offline" if self.offline else "")
                if not ok:
                    if first:
                        self.add("Locked", f"Voice not recognized ({score:.2f})")
                        self.set_status("Locked")
                        time.sleep(1.2)
                        break
                    continue  # someone else talking nearby: ignore it, stay in the conversation
                cleaned = (heard or "").lower().strip(" .!?,")
                if cleaned in SLEEP_WORDS:
                    import tools
                    tools.cancel_pending()  # "stop" also drops a message waiting for yes
                    break
                if cleaned in NOISE_TEXT:
                    continue
                first = False
                last_talk = time.time()
                self.add("You", heard)
                asked_at = time.time()
                if self.offline:
                    import offline
                    reply = offline.handle(heard) or "I'm offline right now, sir, so I can only do basic commands like open apps, time, battery and volume."
                else:
                    reply = self._think(heard)
                self.add("ATOM", reply)
                if self.cancel_event.is_set():
                    break
                self._say(reply)  # saying "hey atom" while it talks just cuts the speech short
                last_talk = time.time()
                import tools
                if tools.MUSIC_STARTED["at"] >= asked_at:
                    break  # music just started: go to standby so it plays at full volume
        except Exception as error:
            print("ATOM error:", type(error).__name__, str(error)[:200])
            self.add("Error", "Something went wrong. Check your connection and try again.")
            self.set_status("Error")
            time.sleep(1.5)
        finally:
            self._release()
            self.set_status("Standing by")

