"""
ui/log_panel.py — Live render log viewer.

Displays per-job log output in a scrolling text widget.
Supports ANSI-style colour tags for status markers emitted by render_script.py.
"""

import tkinter as tk
from tkinter import ttk
from typing import Optional


# Tag names and their visual styles
_TAGS = {
    "header":    {"foreground": "#6a8fb0", "font": ("Courier New", 9, "bold")},
    "success":   {"foreground": "#4caf50"},
    "error":     {"foreground": "#e74c3c"},
    "warning":   {"foreground": "#f39c12"},
    "progress":  {"foreground": "#3d9be9"},
    "normal":    {"foreground": "#c8c8c8"},
    "dim":       {"foreground": "#666666"},
    "command":   {"foreground": "#a9b7c6", "font": ("Courier New", 9, "italic")},
}


def _classify_line(line: str) -> str:
    """Return the tag name for a log line."""
    if "[RenderQueue] Command:" in line:
        return "command"
    if "[RenderQueue] ERROR" in line or "Error" in line or "error" in line:
        return "error"
    if "[RenderQueue] RENDER_COMPLETE" in line:
        return "success"
    if "[RenderQueue] FRAME_DONE" in line:
        return "success"
    if "[RenderQueue] FRAME_START" in line:
        return "progress"
    if "[RenderQueue] WARNING" in line or "Warning" in line:
        return "warning"
    if line.startswith("[RenderQueue]"):
        return "header"
    if line.strip() == "":
        return "dim"
    return "normal"


class LogPanel(ttk.Frame):
    """
    Scrollable log output area.
    Call append(line) from the UI thread to add text.
    Call set_job_log(text) to replace the full content.
    """

    def __init__(self, parent, colors: dict = None, **kwargs):
        super().__init__(parent, style="Panel.TFrame", **kwargs)
        self._colors = colors or {}
        self._build()
        self._auto_scroll = True

    def _build(self):
        C = self._colors
        panel_bg = C.get("panel", "#252526")
        self.rowconfigure(2, weight=1)
        self.columnconfigure(0, weight=1)

        # Header row — row 0
        hdr_frame = tk.Frame(self, bg=panel_bg)
        hdr_frame.grid(row=0, column=0, columnspan=2, sticky=tk.EW)
        tk.Label(hdr_frame, text="RENDER LOG",
                 bg=panel_bg, fg=C.get("text_dim", "#858585"),
                 font=("Segoe UI", 8, "bold")).pack(side=tk.LEFT, padx=10, pady=(8, 4))

        self._auto_scroll_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(hdr_frame, text="Auto-scroll",
                        variable=self._auto_scroll_var,
                        command=self._toggle_auto_scroll).pack(side=tk.RIGHT, padx=8)
        ttk.Button(hdr_frame, text="Clear", width=6, style="Small.TButton",
                   command=self.clear).pack(side=tk.RIGHT, padx=4)

        # Separator — row 1
        tk.Frame(self, height=1, bg=C.get("border", "#3e3e42")).grid(
            row=1, column=0, columnspan=2, sticky=tk.EW)

        # Text widget — row 2
        self._text = tk.Text(
            self,
            wrap=tk.WORD,
            state=tk.DISABLED,
            bg=C.get("log_bg", "#1a1a1a"),
            fg=C.get("text", "#d4d4d4"),
            font=("Courier New", 9),
            insertbackground=C.get("text", "#d4d4d4"),
            relief=tk.FLAT,
            borderwidth=0,
            selectbackground=C.get("card_sel", "#094771"),
        )
        self._text.grid(row=2, column=0, sticky=tk.NSEW)

        self._scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self._text.yview)
        self._scrollbar.grid(row=2, column=1, sticky=tk.NS)
        self._text.configure(yscrollcommand=self._scrollbar.set)

        # Configure colour tags
        for tag, opts in _TAGS.items():
            self._text.tag_configure(tag, **opts)

        # Detect manual scrolling to disable auto-scroll temporarily
        self._text.bind("<MouseWheel>", self._on_manual_scroll)
        self._text.bind("<Button-4>", self._on_manual_scroll)
        self._text.bind("<Button-5>", self._on_manual_scroll)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def append(self, line: str):
        """Append a single line (thread-safe if called via widget.after)."""
        tag = _classify_line(line)
        self._text.configure(state=tk.NORMAL)
        self._text.insert(tk.END, line, tag)
        self._text.configure(state=tk.DISABLED)
        if self._auto_scroll:
            self._text.see(tk.END)

    def set_job_log(self, log: str):
        """Replace the entire log content with the provided text."""
        self._text.configure(state=tk.NORMAL)
        self._text.delete("1.0", tk.END)
        for line in log.splitlines(keepends=True):
            tag = _classify_line(line)
            self._text.insert(tk.END, line, tag)
        self._text.configure(state=tk.DISABLED)
        if self._auto_scroll:
            self._text.see(tk.END)

    def clear(self):
        self._text.configure(state=tk.NORMAL)
        self._text.delete("1.0", tk.END)
        self._text.configure(state=tk.DISABLED)

    # ------------------------------------------------------------------

    def _toggle_auto_scroll(self):
        self._auto_scroll = self._auto_scroll_var.get()
        if self._auto_scroll:
            self._text.see(tk.END)

    def _on_manual_scroll(self, _event=None):
        self._auto_scroll = False
        self._auto_scroll_var.set(False)
