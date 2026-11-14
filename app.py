import threading
import time

from concurrent.futures import ThreadPoolExecutor

import customtkinter as ctk

from stt import record_until_silence, to_wav_bytes, transcribe
from fastbrain import ask
from tts import speak, stop_speaking
from voicelock import check

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class AtomApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("ATOM")
        self.geometry("520x650")
        self.busy = False
        self.cancel_event = threading.Event()

        ctk.CTkLabel(self, text="A T O M", font=("Segoe UI", 34, "bold")).pack(pady=(25, 5))
        self.status = ctk.CTkLabel(self, text="Say Hey Jarvis or click the mic", font=("Segoe UI", 15))
        self.status.pack(pady=5)

        self.mic = ctk.CTkButton(self, text="\U0001F3A4", width=130, height=130, corner_radius=65,
                                 font=("Segoe UI Emoji", 48), command=self.start)
        self.mic.pack(pady=20)
        self.cancel = ctk.CTkButton(self, text="Cancel / Stop", command=self.cancel_current, state="disabled")
        self.cancel.pack(pady=(0, 10))

        self.log = ctk.CTkTextbox(self, width=470, height=280, font=("Segoe UI", 14), wrap="word")
        self.log.pack(pady=10)
        self.bind("<space>", lambda e: self.start())

    def set_status(self, text):
        self.after(0, lambda: self.status.configure(text=text))

    def add(self, who, text):
        def _add():
            self.log.insert("end", f"{who}: {text}\n\n")
            self.log.see("end")
        self.after(0, _add)

    def start(self):
        if self.busy:
            return
        self.busy = True
        self.cancel_event.clear()
        self.mic.configure(fg_color="#c0392b")
        self.cancel.configure(state="normal")
        threading.Thread(target=self.run_turn, daemon=True).start()

    def cancel_current(self):
        self.cancel_event.set()
        stop_speaking()
        self.set_status("Cancelled")

    def run_turn(self):
        try:
            try:
                import comtypes
                comtypes.CoInitialize()  # lets the Windows voice work in this thread
            except Exception:
                pass
            for turn in range(2):
                if self.cancel_event.is_set():
                    break
                if turn:
                    self.set_status("Listening for a follow-up...")
                else:
                    self.set_status("Listening... speak naturally")
                partial_text = {"value": ""}

                def partial_callback(text):
                    partial_text["value"] = text.strip()
                    self.set_status(f"Listening: {text.strip()[:90]}")

                audio = record_until_silence(
                    self.cancel_event,
                    max_seconds=None,
                    on_status=self.set_status,
                    on_partial=partial_callback,
                )
                if audio is None:
                    break
                self.set_status("Verifying voice and recognizing speech...")
                # These jobs are independent once recording finishes. Run both
                # on every activation so the lock stays strict without adding
                # the voice-check time after transcription.
                with ThreadPoolExecutor(max_workers=2) as executor:
                    voice_future = executor.submit(check, audio)
                    text_future = executor.submit(transcribe, to_wav_bytes(audio))
                    ok, score = voice_future.result()
                    heard = text_future.result()
                if partial_text["value"] and (not heard or len(partial_text["value"]) > len(heard)):
                    heard = partial_text["value"]
                if not ok:
                    self.add("Locked", f"Voice not recognized (score {score:.2f})")
                    break
                if not heard or heard.lower().strip(" .!?") in {"stop", "cancel", "never mind"}:
                    break
                self.add("You", heard)
                self.set_status("Thinking...")
                started = time.time()
                reply = ask(heard)
                print("Brain took", round(time.time() - started, 1), "seconds")
                self.add("ATOM", reply)
                if self.cancel_event.is_set():
                    break
                self.set_status("Speaking... press Cancel to stop")
                speak(reply)
        except Exception as error:
            print("ATOM error:", type(error).__name__)
            self.add("Error", "Something went wrong. Check your connection and try again.")
        finally:
            self.busy = False
            self.after(0, lambda: self.mic.configure(fg_color=["#3B8ED0", "#1F6AA5"]))
            self.after(0, lambda: self.cancel.configure(state="disabled"))
            self.set_status("Say Hey Jarvis or click the mic")


if __name__ == "__main__":
    AtomApp().mainloop()
