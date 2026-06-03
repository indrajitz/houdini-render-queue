"""
ui/toolbar.py — Top toolbar with queue control buttons.
"""

import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional


class Toolbar(ttk.Frame):
    """Horizontal toolbar above the main panels."""

    def __init__(self, parent, **callbacks):
        super().__init__(parent, relief=tk.FLAT)

        self._cb = callbacks  # keyed by action name

        self._btn: dict[str, ttk.Button] = {}
        self._build()

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build(self):
        pad = {"padx": 2, "pady": 3}

        def btn(text, key, **kw):
            b = ttk.Button(self, text=text, command=self._cb.get(key), width=kw.get("width", 10))
            b.pack(side=tk.LEFT, **pad)
            self._btn[key] = b
            return b

        # ── Job management ──────────────────────────────────────────
        btn("➕ Add Job", "add_job", width=10)
        btn("✖ Remove", "remove_job", width=9)
        btn("▲ Up", "move_up", width=6)
        btn("▼ Down", "move_down", width=6)

        ttk.Separator(self, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6, pady=2)

        # ── Render control ───────────────────────────────────────────
        btn("▶ Start", "start", width=8)
        btn("⏸ Pause", "pause", width=8)
        btn("⏹ Stop", "stop", width=8)
        btn("⏭ Skip", "skip", width=8)

        ttk.Separator(self, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6, pady=2)

        # ── Queue file ───────────────────────────────────────────────
        btn("💾 Save Queue", "save_queue", width=12)
        btn("📂 Load Queue", "load_queue", width=12)
        btn("🗑 Clear Queue", "clear_queue", width=12)

        self.set_idle_state()

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------

    def _set_states(self, states: dict):
        for key, state in states.items():
            b = self._btn.get(key)
            if b:
                b.config(state=state)

    def set_idle_state(self):
        self._set_states({
            "add_job": tk.NORMAL,
            "remove_job": tk.NORMAL,
            "move_up": tk.NORMAL,
            "move_down": tk.NORMAL,
            "start": tk.NORMAL,
            "pause": tk.DISABLED,
            "stop": tk.DISABLED,
            "skip": tk.DISABLED,
            "save_queue": tk.NORMAL,
            "load_queue": tk.NORMAL,
            "clear_queue": tk.NORMAL,
        })

    def set_rendering_state(self):
        self._set_states({
            "add_job": tk.NORMAL,
            "remove_job": tk.DISABLED,
            "move_up": tk.DISABLED,
            "move_down": tk.DISABLED,
            "start": tk.DISABLED,
            "pause": tk.NORMAL,
            "stop": tk.NORMAL,
            "skip": tk.NORMAL,
            "save_queue": tk.DISABLED,
            "load_queue": tk.DISABLED,
            "clear_queue": tk.DISABLED,
        })

    def set_paused_state(self):
        self._set_states({
            "start": tk.NORMAL,
            "pause": tk.DISABLED,
            "stop": tk.NORMAL,
            "skip": tk.NORMAL,
        })
        self._btn["start"].config(text="▶ Resume")

    def set_resumed_state(self):
        self._set_states({
            "start": tk.DISABLED,
            "pause": tk.NORMAL,
        })
        self._btn["start"].config(text="▶ Start")
