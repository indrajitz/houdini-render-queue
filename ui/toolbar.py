"""
ui/toolbar.py — Top toolbar with queue control buttons.
"""

import tkinter as tk
from tkinter import ttk
from typing import Callable, Dict, Optional


_GROUPS = [
    # (key, label, width)
    [
        ("add_job",    "＋  Add Job",    10),
        ("remove_job", "✕  Remove",      9),
        ("move_up",    "↑",              4),
        ("move_down",  "↓",              4),
    ],
    [
        ("start",      "▶  Start",       9),
        ("pause",      "⏸  Pause",       9),
        ("stop",       "■  Stop",        9),
        ("skip",       "⏭  Skip",        9),
    ],
    [
        ("save_queue",  "Save Queue",    11),
        ("load_queue",  "Load Queue",    11),
        ("clear_queue", "Clear All",     10),
    ],
]


class Toolbar(ttk.Frame):
    def __init__(self, parent, colors: dict = None, **callbacks):
        super().__init__(parent, style="Panel.TFrame")
        self._cb = callbacks
        self._colors = colors or {}
        self._btn: Dict[str, ttk.Button] = {}
        self._build()

    def _build(self):
        C = self._colors
        outer = ttk.Frame(self, style="Panel.TFrame")
        outer.pack(fill=tk.X, padx=8, pady=6)

        for group in _GROUPS:
            for key, label, width in group:
                style = "Accent.TButton" if key == "start" else "TButton"
                b = ttk.Button(
                    outer,
                    text=label,
                    command=self._cb.get(key),
                    width=width,
                    style=style,
                )
                b.pack(side=tk.LEFT, padx=2)
                self._btn[key] = b

            sep = ttk.Frame(outer, width=1, style="TFrame")
            sep.configure(style="TFrame")
            # Visual divider
            div = tk.Frame(outer, width=1, bg=C.get("border", "#3e3e42"))
            div.pack(side=tk.LEFT, fill=tk.Y, padx=8, pady=2)

        self.set_idle_state()

    def _set_states(self, states: dict):
        for key, state in states.items():
            b = self._btn.get(key)
            if b:
                b.config(state=state)

    def set_idle_state(self):
        self._btn.get("start") and self._btn["start"].config(text="▶  Start")
        self._set_states({
            "add_job": tk.NORMAL, "remove_job": tk.NORMAL,
            "move_up": tk.NORMAL, "move_down": tk.NORMAL,
            "start": tk.NORMAL,   "pause": tk.DISABLED,
            "stop": tk.DISABLED,  "skip": tk.DISABLED,
            "save_queue": tk.NORMAL, "load_queue": tk.NORMAL,
            "clear_queue": tk.NORMAL,
        })

    def set_rendering_state(self):
        self._set_states({
            "add_job": tk.NORMAL,  "remove_job": tk.DISABLED,
            "move_up": tk.DISABLED,"move_down": tk.DISABLED,
            "start": tk.DISABLED,  "pause": tk.NORMAL,
            "stop": tk.NORMAL,     "skip": tk.NORMAL,
            "save_queue": tk.DISABLED, "load_queue": tk.DISABLED,
            "clear_queue": tk.DISABLED,
        })

    def set_paused_state(self):
        self._btn["start"].config(text="▶  Resume", style="Accent.TButton")
        self._set_states({
            "start": tk.NORMAL, "pause": tk.DISABLED,
            "stop": tk.NORMAL,  "skip": tk.NORMAL,
        })

    def set_resumed_state(self):
        self._btn["start"].config(text="▶  Start", style="Accent.TButton")
        self._set_states({"start": tk.DISABLED, "pause": tk.NORMAL})
