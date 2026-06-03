"""
ui/queue_panel.py — Left panel showing the job queue as a scrollable list of cards.

Each card displays:
  • Job label / filename
  • ROP path
  • Frame range
  • Status badge
  • Progress bar
  • Enable/disable checkbox
"""

import tkinter as tk
from tkinter import ttk
from typing import Callable, Dict, List, Optional

from queue_manager import RenderJob, JobStatus


# Colour mapping for status badges
_STATUS_COLORS: Dict[str, tuple] = {
    JobStatus.WAITING:   ("#7a8a9a", "#d4d4d4"),   # (badge_bg, badge_fg)
    JobStatus.RENDERING: ("#3d6b9e", "#ffffff"),
    JobStatus.DONE:      ("#2e7d32", "#ffffff"),
    JobStatus.FAILED:    ("#c62828", "#ffffff"),
    JobStatus.SKIPPED:   ("#555555", "#aaaaaa"),
}

_PROGRESS_STYLE: Dict[str, str] = {
    JobStatus.WAITING:   "blue.Horizontal.TProgressbar",
    JobStatus.RENDERING: "blue.Horizontal.TProgressbar",
    JobStatus.DONE:      "green.Horizontal.TProgressbar",
    JobStatus.FAILED:    "red.Horizontal.TProgressbar",
    JobStatus.SKIPPED:   "blue.Horizontal.TProgressbar",
}

_CARD_BG: Dict[str, str] = {
    JobStatus.WAITING:   "#2b2b2b",
    JobStatus.RENDERING: "#1e3a5f",
    JobStatus.DONE:      "#1a3a1a",
    JobStatus.FAILED:    "#3a1a1a",
    JobStatus.SKIPPED:   "#252525",
}

_CARD_BG_SEL = "#3d5a7a"


class JobCard(ttk.Frame):
    """A single job card widget."""

    def __init__(self, parent, job: RenderJob, on_select: Callable, on_toggle: Callable, **kwargs):
        super().__init__(parent, **kwargs)
        self.job = job
        self._on_select = on_select
        self._on_toggle = on_toggle
        self._selected = False
        self._enabled_var = tk.BooleanVar(value=job.enabled)
        self._build()

    def _build(self):
        self.configure(relief=tk.FLAT, borderwidth=1, padding=4)

        # Top row: checkbox + label + status badge
        top = tk.Frame(self, bg=_CARD_BG.get(self.job.status, "#2b2b2b"))
        top.pack(fill=tk.X, expand=False)

        self._chk = tk.Checkbutton(
            top,
            variable=self._enabled_var,
            command=self._toggle_enabled,
            bg=_CARD_BG.get(self.job.status, "#2b2b2b"),
            activebackground=_CARD_BG.get(self.job.status, "#2b2b2b"),
            highlightthickness=0,
            bd=0,
        )
        self._chk.pack(side=tk.LEFT, padx=(0, 2))

        self._lbl_name = tk.Label(
            top,
            text=self._label_text(),
            anchor=tk.W,
            bg=_CARD_BG.get(self.job.status, "#2b2b2b"),
            fg="#d4d4d4",
            font=("Segoe UI", 9, "bold"),
        )
        self._lbl_name.pack(side=tk.LEFT, fill=tk.X, expand=True)

        badge_bg, badge_fg = _STATUS_COLORS.get(self.job.status, ("#555", "#fff"))
        self._badge = tk.Label(
            top,
            text=f" {self.job.status.value} ",
            bg=badge_bg,
            fg=badge_fg,
            font=("Segoe UI", 8, "bold"),
            relief=tk.FLAT,
            padx=4,
            pady=1,
        )
        self._badge.pack(side=tk.RIGHT, padx=(4, 0))

        # Second row: ROP + frames
        card_bg = _CARD_BG.get(self.job.status, "#2b2b2b")
        mid = tk.Frame(self, bg=card_bg)
        mid.pack(fill=tk.X)

        self._lbl_detail = tk.Label(
            mid,
            text=self._detail_text(),
            anchor=tk.W,
            bg=card_bg,
            fg="#888888",
            font=("Segoe UI", 8),
        )
        self._lbl_detail.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self._lbl_frames = tk.Label(
            mid,
            text=self._frames_text(),
            anchor=tk.E,
            bg=card_bg,
            fg="#888888",
            font=("Segoe UI", 8),
        )
        self._lbl_frames.pack(side=tk.RIGHT)

        # Progress bar
        self._progress = ttk.Progressbar(
            self,
            orient=tk.HORIZONTAL,
            mode="determinate",
            style=_PROGRESS_STYLE.get(self.job.status, "blue.Horizontal.TProgressbar"),
            maximum=100,
            value=int(self.job.progress * 100),
        )
        self._progress.pack(fill=tk.X, pady=(3, 0))

        # Bind click events to all sub-widgets
        for w in (self, top, self._lbl_name, self._lbl_detail, self._lbl_frames, mid):
            w.bind("<Button-1>", self._clicked)

    # ------------------------------------------------------------------

    def _label_text(self) -> str:
        import os
        fname = os.path.basename(self.job.hip_file) if self.job.hip_file else "Untitled"
        if self.job.label and self.job.label != fname:
            return f"{self.job.label}  ({fname})"
        return fname or self.job.label or "Untitled Job"

    def _detail_text(self) -> str:
        return f"ROP: {self.job.rop_path}"

    def _frames_text(self) -> str:
        if self.job.status == JobStatus.RENDERING and self.job.total_frames > 0:
            return f"{self.job.frames_done}/{self.job.total_frames} frames"
        step_txt = f"  step {self.job.frame_step}" if self.job.frame_step != 1 else ""
        return f"F {self.job.frame_start}–{self.job.frame_end}{step_txt}"

    def _clicked(self, _event=None):
        self._on_select(self.job.job_id)

    def _toggle_enabled(self):
        self.job.enabled = self._enabled_var.get()
        self._on_toggle(self.job.job_id)

    def set_selected(self, selected: bool):
        self._selected = selected
        bg = _CARD_BG_SEL if selected else _CARD_BG.get(self.job.status, "#2b2b2b")
        self._apply_bg(bg)

    def _apply_bg(self, bg: str):
        try:
            for w in self.winfo_children():
                _set_bg_recursive(w, bg)
        except tk.TclError:
            pass

    def refresh(self):
        """Update card visuals from the job's current state."""
        status = self.job.status
        card_bg = _CARD_BG_SEL if self._selected else _CARD_BG.get(status, "#2b2b2b")
        self._apply_bg(card_bg)

        self._lbl_name.config(text=self._label_text())
        self._lbl_detail.config(text=self._detail_text())
        self._lbl_frames.config(text=self._frames_text())

        badge_bg, badge_fg = _STATUS_COLORS.get(status, ("#555", "#fff"))
        self._badge.config(text=f" {status.value} ", bg=badge_bg, fg=badge_fg)

        pstyle = _PROGRESS_STYLE.get(status, "blue.Horizontal.TProgressbar")
        self._progress.config(style=pstyle, value=int(self.job.progress * 100))

        self._enabled_var.set(self.job.enabled)


def _set_bg_recursive(widget, bg: str):
    try:
        widget.configure(bg=bg)
    except tk.TclError:
        pass
    for child in widget.winfo_children():
        _set_bg_recursive(child, bg)


class QueuePanel(ttk.Frame):
    """
    Scrollable list of JobCard widgets.
    Fires on_select(job_id) and on_toggle(job_id) callbacks.
    """

    def __init__(self, parent,
                 on_select: Optional[Callable] = None,
                 on_toggle: Optional[Callable] = None,
                 **kwargs):
        super().__init__(parent, **kwargs)
        self._on_select = on_select or (lambda jid: None)
        self._on_toggle = on_toggle or (lambda jid: None)
        self._cards: Dict[str, JobCard] = {}          # job_id -> card
        self._selected_id: Optional[str] = None
        self._job_order: List[str] = []               # maintained order
        self._build()

    def _build(self):
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)

        # Header
        hdr = ttk.Label(self, text="RENDER QUEUE", font=("Segoe UI", 9, "bold"),
                        foreground="#6a8fb0")
        hdr.grid(row=0, column=0, columnspan=2, sticky=tk.W, padx=8, pady=(6, 2))

        # Canvas + scrollbar for the card list
        self._canvas = tk.Canvas(self, bg="#2b2b2b", highlightthickness=0, bd=0)
        self._scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL,
                                        command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=self._scrollbar.set)

        self._canvas.grid(row=1, column=0, sticky=tk.NSEW)
        self._scrollbar.grid(row=1, column=1, sticky=tk.NS)

        # Inner frame that holds the cards
        self._inner = tk.Frame(self._canvas, bg="#2b2b2b")
        self._window_id = self._canvas.create_window(
            (0, 0), window=self._inner, anchor=tk.NW, tags="inner"
        )

        self._inner.bind("<Configure>", self._on_inner_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)
        self._canvas.bind("<MouseWheel>", self._on_mousewheel)
        self._canvas.bind("<Button-4>", self._on_mousewheel)
        self._canvas.bind("<Button-5>", self._on_mousewheel)

        # Empty-queue label
        self._empty_lbl = tk.Label(
            self._inner,
            text="Queue is empty.\nClick  ➕ Add Job  to get started.",
            bg="#2b2b2b",
            fg="#555555",
            font=("Segoe UI", 10),
            justify=tk.CENTER,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def rebuild(self, jobs: List[RenderJob]):
        """Completely rebuild card list from the given job list."""
        # Destroy old cards
        for card in self._cards.values():
            card.destroy()
        self._cards.clear()
        self._job_order.clear()

        if not jobs:
            self._empty_lbl.pack(pady=40)
            return

        self._empty_lbl.pack_forget()

        for job in jobs:
            self._job_order.append(job.job_id)
            card = self._make_card(job)
            card.pack(fill=tk.X, padx=4, pady=2)

        # Restore selection highlight
        if self._selected_id and self._selected_id in self._cards:
            self._cards[self._selected_id].set_selected(True)
        elif jobs:
            self._selected_id = jobs[0].job_id
            self._cards[self._selected_id].set_selected(True)

        self._canvas.yview_moveto(0)

    def refresh_card(self, job_id: str):
        """Refresh the visuals of a single card."""
        card = self._cards.get(job_id)
        if card:
            card.refresh()

    def refresh_all_cards(self):
        for card in self._cards.values():
            card.refresh()

    def select(self, job_id: Optional[str]):
        if self._selected_id and self._selected_id in self._cards:
            self._cards[self._selected_id].set_selected(False)
        self._selected_id = job_id
        if job_id and job_id in self._cards:
            self._cards[job_id].set_selected(True)
            self._scroll_to_card(job_id)

    @property
    def selected_id(self) -> Optional[str]:
        return self._selected_id

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _make_card(self, job: RenderJob) -> JobCard:
        card = JobCard(
            self._inner,
            job=job,
            on_select=self._card_selected,
            on_toggle=self._on_toggle,
            style="TFrame",
        )
        self._cards[job.job_id] = card
        return card

    def _card_selected(self, job_id: str):
        self.select(job_id)
        self._on_select(job_id)

    def _on_inner_configure(self, _event=None):
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self._canvas.itemconfig(self._window_id, width=event.width)

    def _on_mousewheel(self, event):
        if event.num == 4:
            self._canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self._canvas.yview_scroll(1, "units")
        else:
            self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _scroll_to_card(self, job_id: str):
        card = self._cards.get(job_id)
        if not card:
            return
        self._inner.update_idletasks()
        card_y = card.winfo_y()
        card_h = card.winfo_height()
        canvas_h = self._canvas.winfo_height()
        total_h = self._inner.winfo_height()
        if total_h <= canvas_h:
            return
        frac_top = card_y / total_h
        frac_bot = (card_y + card_h) / total_h
        cur_top, cur_bot = self._canvas.yview()
        if frac_top < cur_top:
            self._canvas.yview_moveto(frac_top)
        elif frac_bot > cur_bot:
            self._canvas.yview_moveto(frac_bot - (cur_bot - cur_top))
