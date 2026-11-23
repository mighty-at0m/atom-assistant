"""ATOM's window: an Iron Man style HUD with a living arc-reactor ring, captions and controls."""

import math
import threading
import time

import customtkinter as ctk
import tkinter as tk

from engine import Engine

BG = "#04070c"
PANEL = "#0a1420"
DIM = "#0b3a4a"
TEXT = "#bfefff"
MUTED = "#4f7d8c"
STATE_COLORS = {
    "idle": "#00b7d4",
    "listening": "#3df2ff",
    "thinking": "#ffb300",
    "speaking": "#35e0ff",
    "locked": "#ff3b3b",
    "error": "#ff3b3b",
}
STATE_SPEED = {"idle": 0.4, "listening": 1.2, "thinking": 4.5, "speaking": 1.8, "locked": 0.6, "error": 0.3}
ctk.set_appearance_mode("dark")


def _hex(color):
    color = color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


def _mix(a, b, t):
    """Blend colour a towards b by t (0..1)."""
    ra, ga, ba = _hex(a)
    rb, gb, bb = _hex(b)
    return "#%02x%02x%02x" % (int(ra + (rb - ra) * t), int(ga + (gb - ga) * t), int(ba + (bb - ba) * t))


class AtomApp(Engine, ctk.CTk):
    def __init__(self):
        super().__init__(fg_color=BG)
        self.title("ATOM")
        self.geometry("480x720")
        self.minsize(420, 640)
        self.busy = False
        self.cancel_event = threading.Event()
        self.hud_state = "idle"
        self.level = 0.0          # live mic loudness 0..1, drives the core pulse
        self.angle = 0.0
        self.started = time.time()
        self.wake_model = None    # atom.py hands this over so "Hey Jarvis" can interrupt speech

        self._build_top_bar()
        self.canvas = tk.Canvas(self, width=440, height=440, bg=BG, highlightthickness=0)
        self.canvas.pack(pady=(4, 0))
        self._build_reactor()
        self.canvas.bind("<Button-1>", lambda e: self.start())

        self.status = ctk.CTkLabel(self, text="S T A N D I N G   B Y", text_color=STATE_COLORS["idle"],
                                   font=("Consolas", 15, "bold"))
        self.status.pack(pady=(2, 8))

        captions = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=12, border_width=1, border_color=DIM)
        captions.pack(fill="x", padx=20)
        self.you_label = ctk.CTkLabel(captions, text="", text_color=MUTED, font=("Segoe UI", 13),
                                      wraplength=410, justify="left", anchor="w")
        self.you_label.pack(fill="x", padx=14, pady=(10, 2))
        self.atom_label = ctk.CTkLabel(captions, text="Say \"hey atom\" or tap the core.", text_color=TEXT,
                                       font=("Segoe UI", 15), wraplength=410, justify="left", anchor="w")
        self.atom_label.pack(fill="x", padx=14, pady=(2, 12))

        buttons = ctk.CTkFrame(self, fg_color=BG)
        buttons.pack(pady=12)
        style = dict(width=120, height=34, corner_radius=17, fg_color=PANEL, border_width=1,
                     border_color=STATE_COLORS["idle"], hover_color=DIM, text_color=TEXT, font=("Consolas", 13, "bold"))
        ctk.CTkButton(buttons, text="◉  TALK", command=self.start, **style).pack(side="left", padx=6)
        self.cancel = ctk.CTkButton(buttons, text="■  STOP", command=self.cancel_current, **style)
        self.cancel.pack(side="left", padx=6)
        ctk.CTkButton(buttons, text="≡  LOG", command=self.toggle_log, **style).pack(side="left", padx=6)

        self.log = ctk.CTkTextbox(self, height=150, fg_color=PANEL, text_color=TEXT, font=("Consolas", 12),
                                  border_width=1, border_color=DIM, wrap="word")
        self.log_visible = False
        self.mic = self.cancel  # kept for older code that recolours the mic button
        self.bind("<space>", lambda e: self.start())
        self.bind("<Escape>", lambda e: self.cancel_current())
        self._animate()
        self._tick_clock()

    # ---- HUD drawing ---------------------------------------------------------

    def _build_top_bar(self):
        bar = ctk.CTkFrame(self, fg_color=BG)
        bar.pack(fill="x", padx=18, pady=(12, 0))
        self.clock = ctk.CTkLabel(bar, text="", text_color=MUTED, font=("Consolas", 13))
        self.clock.pack(side="left")
        self.battery = ctk.CTkLabel(bar, text="", text_color=MUTED, font=("Consolas", 13))
        self.battery.pack(side="right")
        ctk.CTkLabel(bar, text="A.T.O.M", text_color=STATE_COLORS["idle"], font=("Consolas", 16, "bold")).pack()

    def _build_reactor(self):
        c, cx, cy = self.canvas, 220, 220
        self.cx, self.cy = cx, cy
        c.create_oval(cx - 200, cy - 200, cx + 200, cy + 200, outline=DIM, width=1)
        c.create_oval(cx - 120, cy - 120, cx + 120, cy + 120, outline=DIM, width=1)
        self.ticks = []
        for i in range(72):
            a = math.radians(i * 5)
            r1, r2 = (176, 190) if i % 6 == 0 else (182, 190)
            self.ticks.append(c.create_line(cx + r1 * math.cos(a), cy + r1 * math.sin(a),
                                            cx + r2 * math.cos(a), cy + r2 * math.sin(a), fill=DIM, width=2))
        self.outer_arcs = [c.create_arc(cx - 162, cy - 162, cx + 162, cy + 162, style="arc", width=5,
                                        outline=STATE_COLORS["idle"], start=i * 120, extent=70) for i in range(3)]
        self.inner_arcs = [c.create_arc(cx - 138, cy - 138, cx + 138, cy + 138, style="arc", width=2,
                                        outline=STATE_COLORS["idle"], start=i * 180, extent=110) for i in range(2)]
        self.glow = [c.create_oval(0, 0, 0, 0, outline="", fill=BG) for _ in range(6)]
        self.core_ring = c.create_oval(0, 0, 0, 0, outline=STATE_COLORS["idle"], width=3)
        self.core_text = c.create_text(cx, cy, text="ATOM", fill=BG, font=("Consolas", 20, "bold"))

    def _animate(self):
        color = STATE_COLORS.get(self.hud_state, STATE_COLORS["idle"])
        t = time.time() - self.started
        self.angle = (self.angle + STATE_SPEED.get(self.hud_state, 1)) % 360
        c, cx, cy = self.canvas, self.cx, self.cy

        for i, arc in enumerate(self.outer_arcs):
            c.itemconfig(arc, start=(self.angle + i * 120) % 360, outline=color)
        for i, arc in enumerate(self.inner_arcs):
            c.itemconfig(arc, start=(-self.angle * 1.6 + i * 180) % 360, outline=_mix(color, BG, 0.35))

        sweep = (self.angle * 2) % 360
        for i, tick in enumerate(self.ticks):
            distance = abs((i * 5 - sweep + 180) % 360 - 180)
            c.itemconfig(tick, fill=_mix(color, DIM, min(1.0, distance / 60)))

        if self.hud_state == "listening":
            pulse = 0.25 + 0.75 * self.level
        elif self.hud_state == "speaking":
            pulse = 0.5 + 0.5 * abs(math.sin(t * 7)) * abs(math.sin(t * 2.3))
        elif self.hud_state == "thinking":
            pulse = 0.5 + 0.2 * math.sin(t * 6)
        else:
            pulse = 0.35 + 0.15 * math.sin(t * 1.5)
        radius = 52 + 14 * pulse
        for i, oval in enumerate(self.glow):
            r = radius + (5 - i) * 7 * (0.6 + pulse)
            c.coords(oval, cx - r, cy - r, cx + r, cy + r)
            c.itemconfig(oval, fill=_mix(BG, color, (i + 1) / 7 * (0.45 + 0.55 * pulse)))
        c.coords(self.core_ring, cx - radius - 4, cy - radius - 4, cx + radius + 4, cy + radius + 4)
        c.itemconfig(self.core_ring, outline=color)
        self.level *= 0.85
        self.after(33, self._animate)

    def _tick_clock(self):
        self.clock.configure(text=time.strftime("%H:%M  %a %d %b"))
        if int(time.time()) % 60 < 2 or not self.battery.cget("text"):
            try:
                from tools import get_battery_status
                message = get_battery_status()["message"]
                digits = "".join(ch for ch in message.split("%")[0] if ch.isdigit())
                self.battery.configure(text=f"PWR {digits}%" + (" ⚡" if "plugged" in message else ""))
            except Exception:
                pass
        self.after(1000, self._tick_clock)

    # ---- State and text ------------------------------------------------------

    def set_state(self, state):
        self.after(0, lambda: setattr(self, "hud_state", state))

    def set_status(self, text):
        lowered = text.lower()
        if "listening" in lowered:
            state = "listening"
        elif "thinking" in lowered or "verifying" in lowered or "recogniz" in lowered or "working" in lowered:
            state = "thinking"
        elif "speaking" in lowered:
            state = "speaking"
        elif "locked" in lowered or "error" in lowered:
            state = "locked"
        else:
            state = "idle"
        spaced = "   ".join(" ".join(word) for word in text.upper().split())
        self.after(0, lambda: (setattr(self, "hud_state", state),
                               self.status.configure(text=spaced[:60], text_color=STATE_COLORS[state])))

    def set_level(self, level):
        self.level = max(self.level, level)

    def add(self, who, text):
        def update():
            if who == "You":
                self.you_label.configure(text="YOU  ›  " + text)
            elif who == "ATOM":
                self.atom_label.configure(text=text)
            else:
                self.atom_label.configure(text=f"{who}: {text}")
            self.log.insert("end", f"{who}: {text}\n\n")
            self.log.see("end")
        self.after(0, update)

    # ---- Window control (the same names ui_web.WebApp has, so atom.py works with either) ----

    def show_window(self):
        self.deiconify()
        self.lift()
        self.attributes("-topmost", True)
        self.after(500, lambda: self.attributes("-topmost", False))
        self.focus_force()

    def hide_window(self):
        self.withdraw()

    def quit_app(self):
        self.destroy()

    def close_to_tray(self):
        self.protocol("WM_DELETE_WINDOW", self.withdraw)

    def toggle_log(self):
        if self.log_visible:
            self.log.pack_forget()
        else:
            self.log.pack(fill="both", expand=True, padx=20, pady=(0, 14))
        self.log_visible = not self.log_visible



if __name__ == "__main__":
    AtomApp().mainloop()
