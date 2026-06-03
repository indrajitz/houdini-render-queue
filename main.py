"""
main.py — Entry point for the Houdini Render Queue application.
"""

import sys
import tkinter as tk
from tkinter import ttk

# Ensure the project root is on the path so sibling modules resolve correctly
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ui.main_window import MainWindow


def main():
    root = tk.Tk()
    root.title("Houdini Render Queue")
    root.geometry("1200x750")
    root.minsize(900, 600)

    # Apply a reasonably modern ttk theme
    style = ttk.Style(root)
    available = style.theme_names()
    for preferred in ("clam", "alt", "default"):
        if preferred in available:
            style.theme_use(preferred)
            break

    # Custom colours that feel professional
    _configure_styles(style)

    app = MainWindow(root)
    app.pack(fill=tk.BOTH, expand=True)

    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


def _configure_styles(style: ttk.Style):
    """Define custom widget styles used throughout the application."""
    bg = "#2b2b2b"
    fg = "#d4d4d4"
    sel_bg = "#3d6b9e"
    btn_bg = "#3c3f41"
    btn_active = "#4c5052"
    entry_bg = "#3c3f41"
    frame_bg = "#2b2b2b"
    separator = "#555555"

    style.configure(".", background=bg, foreground=fg, font=("Segoe UI", 9))
    style.configure("TFrame", background=frame_bg)
    style.configure("TLabel", background=frame_bg, foreground=fg)
    style.configure("TLabelframe", background=frame_bg, foreground=fg)
    style.configure("TLabelframe.Label", background=frame_bg, foreground="#a9b7c6", font=("Segoe UI", 9, "bold"))
    style.configure("TEntry", fieldbackground=entry_bg, foreground=fg, insertcolor=fg)
    style.configure("TSpinbox", fieldbackground=entry_bg, foreground=fg, insertcolor=fg)
    style.configure("TSeparator", background=separator)

    style.configure(
        "TButton",
        background=btn_bg,
        foreground=fg,
        relief=tk.FLAT,
        borderwidth=1,
        focusthickness=0,
    )
    style.map(
        "TButton",
        background=[("active", btn_active), ("disabled", "#333333")],
        foreground=[("disabled", "#666666")],
    )

    style.configure(
        "Toolbar.TButton",
        background=btn_bg,
        foreground=fg,
        padding=(6, 4),
        relief=tk.FLAT,
    )
    style.map(
        "Toolbar.TButton",
        background=[("active", btn_active), ("disabled", "#333333")],
        foreground=[("disabled", "#666666")],
    )

    style.configure("TScrollbar", background=btn_bg, troughcolor=frame_bg, arrowcolor=fg)

    # Notebook (tabs)
    style.configure("TNotebook", background=bg, tabmargins=[0, 0, 0, 0])
    style.configure("TNotebook.Tab", background=btn_bg, foreground=fg, padding=[8, 3])
    style.map("TNotebook.Tab", background=[("selected", sel_bg)], foreground=[("selected", "#ffffff")])

    # Progress bar
    style.configure("green.Horizontal.TProgressbar", troughcolor=entry_bg, background="#4caf50")
    style.configure("red.Horizontal.TProgressbar", troughcolor=entry_bg, background="#e74c3c")
    style.configure("blue.Horizontal.TProgressbar", troughcolor=entry_bg, background=sel_bg)

    # Status colours for job cards
    style.configure("Waiting.TFrame", background=frame_bg)
    style.configure("Rendering.TFrame", background="#1e3a5f")
    style.configure("Done.TFrame", background="#1a3a1a")
    style.configure("Failed.TFrame", background="#3a1a1a")
    style.configure("Skipped.TFrame", background="#2a2a2a")

    style.configure("StatusBar.TFrame", background="#1e1e1e")
    style.configure("StatusBar.TLabel", background="#1e1e1e", foreground="#a9b7c6")

    # Checkbutton
    style.configure("TCheckbutton", background=frame_bg, foreground=fg)
    style.map("TCheckbutton", background=[("active", frame_bg)])


if __name__ == "__main__":
    main()
