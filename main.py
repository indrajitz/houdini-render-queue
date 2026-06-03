"""
main.py — Entry point for the Houdini Render Queue application.

Tries to use TkinterDnD2 for OS-level file drag-and-drop; falls back
to plain tkinter if the package is not installed.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tkinter as tk
from tkinter import ttk

# Attempt to import TkinterDnD2 for OS-level file drop support
try:
    from tkinterdnd2 import TkinterDnD
    _DND_AVAILABLE = True
except ImportError:
    _DND_AVAILABLE = False

from ui.main_window import MainWindow

# ── Colour palette ────────────────────────────────────────────────────────────
COLORS = {
    "bg":          "#1e1e1e",
    "panel":       "#252526",
    "card":        "#2d2d30",
    "card_sel":    "#094771",
    "border":      "#3e3e42",
    "accent":      "#007acc",
    "accent_hover":"#1a8ad4",
    "success":     "#4ec9b0",
    "error":       "#f44747",
    "warning":     "#ce9178",
    "text":        "#d4d4d4",
    "text_dim":    "#858585",
    "text_bright": "#ffffff",
    "btn":         "#3a3d41",
    "btn_hover":   "#45494e",
    "btn_active":  "#007acc",
    "entry":       "#3c3c3c",
    "log_bg":      "#1a1a1a",
    "status_bar":  "#007acc",
}


def build_styles(style: ttk.Style):
    C = COLORS
    base_font  = ("Segoe UI", 9)
    bold_font  = ("Segoe UI", 9, "bold")

    style.configure(".",
        background=C["bg"],
        foreground=C["text"],
        font=base_font,
        borderwidth=0,
        relief="flat",
    )
    style.configure("TFrame",       background=C["bg"])
    style.configure("Panel.TFrame", background=C["panel"])
    style.configure("Card.TFrame",  background=C["card"])

    style.configure("TLabel",       background=C["bg"],    foreground=C["text"])
    style.configure("Panel.TLabel", background=C["panel"], foreground=C["text"])
    style.configure("Dim.TLabel",   background=C["bg"],    foreground=C["text_dim"])
    style.configure("Accent.TLabel",background=C["bg"],    foreground=C["accent"])
    style.configure("Section.TLabel",
        background=C["panel"], foreground=C["text_dim"],
        font=("Segoe UI", 8, "bold"),
    )

    style.configure("TLabelframe",
        background=C["panel"], foreground=C["text_dim"],
        bordercolor=C["border"],
    )
    style.configure("TLabelframe.Label",
        background=C["panel"], foreground=C["text_dim"],
        font=("Segoe UI", 8, "bold"),
    )

    style.configure("TEntry",
        fieldbackground=C["entry"],
        foreground=C["text"],
        insertcolor=C["text"],
        bordercolor=C["border"],
        lightcolor=C["border"],
        darkcolor=C["border"],
    )
    style.configure("TCombobox",
        fieldbackground=C["entry"],
        foreground=C["text"],
        background=C["btn"],
        arrowcolor=C["text_dim"],
        selectbackground=C["card_sel"],
        selectforeground=C["text_bright"],
    )
    style.map("TCombobox",
        fieldbackground=[("readonly", C["entry"])],
        foreground=[("readonly", C["text"])],
    )
    style.configure("TSpinbox",
        fieldbackground=C["entry"],
        foreground=C["text"],
        insertcolor=C["text"],
        arrowcolor=C["text_dim"],
        background=C["btn"],
    )

    style.configure("TButton",
        background=C["btn"],
        foreground=C["text"],
        padding=(8, 4),
        relief="flat",
        focusthickness=0,
    )
    style.map("TButton",
        background=[("active", C["btn_hover"]), ("disabled", C["card"]), ("pressed", C["accent"])],
        foreground=[("disabled", C["text_dim"])],
    )

    style.configure("Accent.TButton",
        background=C["accent"],
        foreground=C["text_bright"],
        padding=(10, 5),
        font=bold_font,
    )
    style.map("Accent.TButton",
        background=[("active", C["accent_hover"]), ("disabled", C["card"])],
        foreground=[("disabled", C["text_dim"])],
    )

    style.configure("Small.TButton",
        background=C["btn"],
        foreground=C["text"],
        padding=(4, 2),
        font=("Segoe UI", 8),
    )
    style.map("Small.TButton",
        background=[("active", C["btn_hover"]), ("disabled", C["card"])],
    )

    style.configure("TScrollbar",
        background=C["card"],
        troughcolor=C["bg"],
        arrowcolor=C["text_dim"],
        bordercolor=C["bg"],
        lightcolor=C["bg"],
        darkcolor=C["bg"],
    )

    style.configure("TNotebook",        background=C["bg"],    tabmargins=0)
    style.configure("TNotebook.Tab",    background=C["card"],  foreground=C["text_dim"],  padding=(10, 4))
    style.map("TNotebook.Tab",
        background=[("selected", C["panel"])],
        foreground=[("selected", C["text"])],
    )

    style.configure("TCheckbutton", background=C["panel"], foreground=C["text"])
    style.map("TCheckbutton",
        background=[("active", C["panel"])],
        indicatorcolor=[("selected", C["accent"]), ("!selected", C["entry"])],
    )

    style.configure("TSeparator", background=C["border"])
    style.configure("TPanedwindow", background=C["border"])
    style.configure("Sash", sashpad=2, sashrelief="flat", background=C["border"])

    style.configure("green.Horizontal.TProgressbar",
        troughcolor=C["card"], background=C["success"])
    style.configure("blue.Horizontal.TProgressbar",
        troughcolor=C["card"], background=C["accent"])
    style.configure("red.Horizontal.TProgressbar",
        troughcolor=C["card"], background=C["error"])
    style.configure("grey.Horizontal.TProgressbar",
        troughcolor=C["card"], background=C["text_dim"])

    style.configure("StatusBar.TFrame", background=C["bg"])
    style.configure("StatusBar.TLabel", background=C["bg"], foreground=C["text_dim"],
                    font=("Segoe UI", 8))


def main():
    if _DND_AVAILABLE:
        root = TkinterDnD.Tk()
    else:
        root = tk.Tk()

    root.title("Houdini Render Queue")
    root.geometry("1280x800")
    root.minsize(1000, 640)
    root.configure(bg=COLORS["bg"])

    style = ttk.Style(root)
    available = style.theme_names()
    for preferred in ("clam", "alt", "default"):
        if preferred in available:
            style.theme_use(preferred)
            break

    build_styles(style)

    app = MainWindow(root, dnd_available=_DND_AVAILABLE, colors=COLORS)
    app.pack(fill=tk.BOTH, expand=True)

    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
