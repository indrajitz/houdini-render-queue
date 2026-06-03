"""
ui/queue_panel.py — Left panel: scrollable job queue with drag-to-reorder
and OS-level file drop support (requires tkinterdnd2).

Each job card shows:
  • Coloured left-side status stripe
  • Job label / filename
  • ROP path and type
  • Frame range  (or live progress during render)
  • Output path (truncated)
  • Progress bar
"""

import os
import tkinter as tk
from tkinter import ttk
from typing import Callable, Dict, List, Optional

from queue_manager import RenderJob, JobStatus

# ── Status colours ─────────────────────────────────────────────────────────────
_STATUS_STRIPE: Dict[str, str] = {
    JobStatus.WAITING:   "#4a4a4a",
    JobStatus.RENDERING: "#007acc",
    JobStatus.DONE:      "#4ec9b0",
    JobStatus.FAILED:    "#f44747",
    JobStatus.SKIPPED:   "#555555",
}
_STATUS_BADGE_BG: Dict[str, str] = {
    JobStatus.WAITING:   "#3a3a3a",
    JobStatus.RENDERING: "#094771",
    JobStatus.DONE:      "#1b4a3e",
    JobStatus.FAILED:    "#4a1a1a",
    JobStatus.SKIPPED:   "#2a2a2a",
}
_STATUS_BADGE_FG: Dict[str, str] = {
    JobStatus.WAITING:   "#858585",
    JobStatus.RENDERING: "#75beff",
    JobStatus.DONE:      "#4ec9b0",
    JobStatus.FAILED:    "#f44747",
    JobStatus.SKIPPED:   "#555555",
}
_CARD_BG     = "#2d2d30"
_CARD_BG_SEL = "#094771"
_CARD_HOVER  = "#37373d"

_PROGRESS_STYLE = {
    JobStatus.WAITING:   "grey.Horizontal.TProgressbar",
    JobStatus.RENDERING: "blue.Horizontal.TProgressbar",
    JobStatus.DONE:      "green.Horizontal.TProgressbar",
    JobStatus.FAILED:    "red.Horizontal.TProgressbar",
    JobStatus.SKIPPED:   "grey.Horizontal.TProgressbar",
}


class JobCard(tk.Frame):
    """A single rendered job card."""

    HEIGHT = 72   # approximate px

    def __init__(self, parent, job: RenderJob,
                 on_select: Callable, on_toggle: Callable,
                 on_drag_start: Callable, colors: dict, **kwargs):
        super().__init__(parent, bg=_CARD_BG, **kwargs)
        self.job = job
        self._on_select   = on_select
        self._on_toggle   = on_toggle
        self._on_drag_start = on_drag_start
        self._colors      = colors
        self._selected    = False
        self._enabled_var = tk.BooleanVar(value=job.enabled)
        self._build()

    def _build(self):
        C = self._colors
        status = self.job.status

        # ── Left status stripe ─────────────────────────────────────────
        stripe_color = _STATUS_STRIPE.get(status, "#4a4a4a")
        self._stripe = tk.Frame(self, width=4, bg=stripe_color)
        self._stripe.pack(side=tk.LEFT, fill=tk.Y)

        # ── Drag handle ────────────────────────────────────────────────
        self._handle = tk.Label(
            self, text="⠿", bg=_CARD_BG, fg="#555555",
            font=("Segoe UI", 11), cursor="fleur",
            width=1,
        )
        self._handle.pack(side=tk.LEFT, padx=(4, 0), fill=tk.Y)
        self._handle.bind("<ButtonPress-1>",   self._drag_press)
        self._handle.bind("<B1-Motion>",       self._drag_motion)
        self._handle.bind("<ButtonRelease-1>", self._drag_release)

        # ── Main content ───────────────────────────────────────────────
        content = tk.Frame(self, bg=_CARD_BG)
        content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(6, 6), pady=6)

        # Row 1: checkbox + label + status badge
        row1 = tk.Frame(content, bg=_CARD_BG)
        row1.pack(fill=tk.X)

        self._chk = tk.Checkbutton(
            row1,
            variable=self._enabled_var,
            command=self._toggle_enabled,
            bg=_CARD_BG,
            activebackground=_CARD_BG,
            selectcolor=C.get("entry", "#3c3c3c"),
            highlightthickness=0,
            bd=0,
        )
        self._chk.pack(side=tk.LEFT)

        self._lbl_name = tk.Label(
            row1, text=self._name_text(),
            bg=_CARD_BG, fg=C.get("text", "#d4d4d4"),
            font=("Segoe UI", 9, "bold"),
            anchor=tk.W,
        )
        self._lbl_name.pack(side=tk.LEFT, fill=tk.X, expand=True)

        badge_bg = _STATUS_BADGE_BG.get(status, "#3a3a3a")
        badge_fg = _STATUS_BADGE_FG.get(status, "#858585")
        self._badge = tk.Label(
            row1,
            text=f" {status.value} ",
            bg=badge_bg, fg=badge_fg,
            font=("Segoe UI", 7, "bold"),
            padx=5, pady=2,
        )
        self._badge.pack(side=tk.RIGHT)

        # Row 2: ROP path
        row2 = tk.Frame(content, bg=_CARD_BG)
        row2.pack(fill=tk.X, pady=(1, 0))
        self._lbl_rop = tk.Label(
            row2, text=self._rop_text(),
            bg=_CARD_BG, fg=C.get("text_dim", "#858585"),
            font=("Courier New", 8),
            anchor=tk.W,
        )
        self._lbl_rop.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self._lbl_frames = tk.Label(
            row2, text=self._frames_text(),
            bg=_CARD_BG, fg=C.get("accent", "#007acc"),
            font=("Segoe UI", 8),
            anchor=tk.E,
        )
        self._lbl_frames.pack(side=tk.RIGHT)

        # Row 3: output path (truncated)
        self._lbl_output = tk.Label(
            content, text=self._output_text(),
            bg=_CARD_BG, fg=C.get("text_dim", "#858585"),
            font=("Segoe UI", 8),
            anchor=tk.W,
        )
        self._lbl_output.pack(fill=tk.X)

        # Progress bar
        self._progress = ttk.Progressbar(
            content,
            orient=tk.HORIZONTAL,
            mode="determinate",
            style=_PROGRESS_STYLE.get(status, "grey.Horizontal.TProgressbar"),
            maximum=100,
            value=int(self.job.progress * 100),
        )
        self._progress.pack(fill=tk.X, pady=(3, 0))

        # ── Bind click on all subwidgets ───────────────────────────────
        for w in self._all_widgets():
            if w not in (self._chk, self._handle):
                w.bind("<Button-1>", self._clicked)
                w.bind("<Enter>",    self._hovered)
                w.bind("<Leave>",    self._unhovered)

        self.bind("<Button-1>", self._clicked)
        self.bind("<Enter>",    self._hovered)
        self.bind("<Leave>",    self._unhovered)

    # ── Text helpers ───────────────────────────────────────────────────

    def _name_text(self) -> str:
        fname = os.path.basename(self.job.hip_file) if self.job.hip_file else "Untitled"
        label = self.job.label
        if label and label != fname:
            return f"{label}"
        return fname or "Untitled Job"

    def _rop_text(self) -> str:
        rop = self.job.rop_path or "—"
        return f"ROP  {rop}"

    def _frames_text(self) -> str:
        if self.job.status == JobStatus.RENDERING and self.job.total_frames > 0:
            return f"{self.job.frames_done}/{self.job.total_frames} frames"
        s, e, st = self.job.frame_start, self.job.frame_end, self.job.frame_step
        step_txt = f"  ×{st}" if st != 1 else ""
        return f"F {s} – {e}{step_txt}"

    def _output_text(self) -> str:
        path = self.job.output_dir or self.job.rop_output_path or ""
        if not path:
            return ""
        # Truncate from the left
        if len(path) > 52:
            path = "…" + path[-49:]
        return f"↳  {path}"

    # ── Event handlers ─────────────────────────────────────────────────

    def _clicked(self, _e=None):
        self._on_select(self.job.job_id)

    def _toggle_enabled(self):
        self.job.enabled = self._enabled_var.get()
        self._on_toggle(self.job.job_id)

    def _hovered(self, _e=None):
        if not self._selected:
            self._set_bg(_CARD_HOVER)

    def _unhovered(self, _e=None):
        if not self._selected:
            self._set_bg(_CARD_BG)

    def _drag_press(self, event):
        self._on_drag_start(self.job.job_id, event)

    def _drag_motion(self, event):
        self.event_generate("<<DragMotion>>", x=event.x_root, y=event.y_root)

    def _drag_release(self, event):
        self.event_generate("<<DragRelease>>", x=event.x_root, y=event.y_root)

    # ── Visuals ────────────────────────────────────────────────────────

    def set_selected(self, selected: bool):
        self._selected = selected
        bg = _CARD_BG_SEL if selected else _CARD_BG
        self._set_bg(bg)

    def _set_bg(self, bg: str):
        self.configure(bg=bg)
        for w in self._all_widgets():
            try:
                w.configure(bg=bg)
            except tk.TclError:
                pass
        self._stripe.configure(bg=_STATUS_STRIPE.get(self.job.status, "#4a4a4a"))

    def refresh(self):
        status = self.job.status
        bg = _CARD_BG_SEL if self._selected else _CARD_BG
        self._set_bg(bg)
        self._stripe.configure(bg=_STATUS_STRIPE.get(status, "#4a4a4a"))
        self._lbl_name.config(text=self._name_text())
        self._lbl_rop.config(text=self._rop_text())
        self._lbl_frames.config(text=self._frames_text())
        self._lbl_output.config(text=self._output_text())
        self._badge.config(
            text=f" {status.value} ",
            bg=_STATUS_BADGE_BG.get(status, "#3a3a3a"),
            fg=_STATUS_BADGE_FG.get(status, "#858585"),
        )
        pstyle = _PROGRESS_STYLE.get(status, "grey.Horizontal.TProgressbar")
        self._progress.config(style=pstyle, value=int(self.job.progress * 100))
        self._enabled_var.set(self.job.enabled)

    def _all_widgets(self):
        result = [self]
        queue = list(self.winfo_children())
        while queue:
            w = queue.pop()
            result.append(w)
            queue.extend(w.winfo_children())
        return result


# ── Drop indicator (a thin horizontal line) ───────────────────────────────────

class _DropIndicator(tk.Frame):
    def __init__(self, parent, color="#007acc"):
        super().__init__(parent, height=2, bg=color)


# ── QueuePanel ────────────────────────────────────────────────────────────────

class QueuePanel(ttk.Frame):
    """
    Scrollable list of JobCards with:
      • OS file drag-and-drop (requires tkinterdnd2)
      • Internal drag-to-reorder
    """

    def __init__(self, parent,
                 on_select: Optional[Callable] = None,
                 on_toggle: Optional[Callable] = None,
                 on_reorder: Optional[Callable] = None,
                 on_files_dropped: Optional[Callable] = None,
                 dnd_available: bool = False,
                 colors: dict = None,
                 **kwargs):
        super().__init__(parent, style="Panel.TFrame", **kwargs)
        self._on_select       = on_select       or (lambda jid: None)
        self._on_toggle       = on_toggle       or (lambda jid: None)
        self._on_reorder      = on_reorder      or (lambda jid, target_idx: None)
        self._on_files_dropped = on_files_dropped or (lambda paths: None)
        self._dnd_available   = dnd_available
        self._colors          = colors or {}
        self._cards: Dict[str, JobCard] = {}
        self._job_order: List[str] = []
        self._selected_id: Optional[str] = None

        # Drag-reorder state
        self._drag_job_id: Optional[str] = None
        self._indicator: Optional[_DropIndicator] = None
        self._drag_target_idx: int = -1

        self._build()

    def _build(self):
        C = self._colors
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)

        # Header
        hdr = tk.Frame(self, bg=C.get("panel", "#252526"))
        hdr.grid(row=0, column=0, columnspan=2, sticky=tk.EW)
        tk.Label(
            hdr, text="RENDER QUEUE",
            bg=C.get("panel", "#252526"),
            fg=C.get("text_dim", "#858585"),
            font=("Segoe UI", 8, "bold"),
        ).pack(side=tk.LEFT, padx=10, pady=(8, 4))

        if self._dnd_available:
            tk.Label(
                hdr,
                text="Drop .hip files here",
                bg=C.get("panel", "#252526"),
                fg=C.get("text_dim", "#555"),
                font=("Segoe UI", 8, "italic"),
            ).pack(side=tk.RIGHT, padx=10)

        # Canvas + scrollbar
        self._canvas = tk.Canvas(
            self, bg=C.get("panel", "#252526"),
            highlightthickness=0, bd=0,
        )
        self._scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL,
                                         command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=self._scrollbar.set)
        self._canvas.grid(row=1, column=0, sticky=tk.NSEW)
        self._scrollbar.grid(row=1, column=1, sticky=tk.NS)

        # Inner frame for cards
        self._inner = tk.Frame(self._canvas, bg=C.get("panel", "#252526"))
        self._window_id = self._canvas.create_window(
            (0, 0), window=self._inner, anchor=tk.NW, tags="inner")

        self._inner.bind("<Configure>", self._on_inner_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)
        self._canvas.bind("<MouseWheel>", self._on_mousewheel)
        self._canvas.bind("<Button-4>",   self._on_mousewheel)
        self._canvas.bind("<Button-5>",   self._on_mousewheel)

        # Drag-reorder bindings on inner frame
        self._inner.bind("<<DragMotion>>",  self._drag_motion, add=True)
        self._inner.bind("<<DragRelease>>", self._drag_release, add=True)

        # Empty queue placeholder
        self._empty_lbl = tk.Label(
            self._inner,
            text="No jobs in queue.\n\nClick  ＋ Add Job  or\ndrop .hip files here.",
            bg=C.get("panel", "#252526"),
            fg=C.get("text_dim", "#555555"),
            font=("Segoe UI", 10),
            justify=tk.CENTER,
        )

        # OS file drag-and-drop
        if self._dnd_available:
            try:
                from tkinterdnd2 import DND_FILES
                self._canvas.drop_target_register(DND_FILES)
                self._canvas.dnd_bind("<<Drop>>", self._handle_file_drop)
                self._inner.drop_target_register(DND_FILES)
                self._inner.dnd_bind("<<Drop>>", self._handle_file_drop)
            except Exception:
                pass

    # ── Public API ─────────────────────────────────────────────────────

    def rebuild(self, jobs: List[RenderJob]):
        for card in self._cards.values():
            card.destroy()
        self._cards.clear()
        self._job_order.clear()

        if not jobs:
            self._empty_lbl.pack(pady=60)
            return
        self._empty_lbl.pack_forget()

        for job in jobs:
            self._job_order.append(job.job_id)
            card = self._make_card(job)
            card.pack(fill=tk.X, padx=6, pady=3)

        # Restore selection
        if self._selected_id and self._selected_id in self._cards:
            self._cards[self._selected_id].set_selected(True)
        elif jobs:
            self._selected_id = jobs[0].job_id
            self._cards[self._selected_id].set_selected(True)

        self._canvas.yview_moveto(0)

    def refresh_card(self, job_id: str):
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

    # ── Internal helpers ───────────────────────────────────────────────

    def _make_card(self, job: RenderJob) -> JobCard:
        card = JobCard(
            self._inner,
            job=job,
            on_select=self._card_selected,
            on_toggle=self._on_toggle,
            on_drag_start=self._drag_start,
            colors=self._colors,
        )
        # Propagate drag events from card children upward
        card.bind("<<DragMotion>>",  self._drag_motion, add=True)
        card.bind("<<DragRelease>>", self._drag_release, add=True)
        self._cards[job.job_id] = card
        return card

    def _card_selected(self, job_id: str):
        self.select(job_id)
        self._on_select(job_id)

    # ── OS file drop ───────────────────────────────────────────────────

    def _handle_file_drop(self, event):
        raw = event.data
        # tkinterdnd2 returns paths as a Tcl list string; parse it
        paths = self._parse_drop_data(raw)
        hip_paths = [p for p in paths
                     if p.lower().endswith((".hip", ".hipnc", ".hiplc"))]
        if hip_paths:
            self._on_files_dropped(hip_paths)

    @staticmethod
    def _parse_drop_data(raw: str) -> List[str]:
        """Parse Tcl list — handles paths with spaces wrapped in braces."""
        import re
        paths = []
        # Braced groups first
        for m in re.finditer(r"\{([^}]+)\}", raw):
            paths.append(m.group(1))
            raw = raw.replace(m.group(0), "", 1)
        # Remaining space-separated tokens
        paths.extend(t for t in raw.split() if t)
        return paths

    # ── Drag-to-reorder ────────────────────────────────────────────────

    def _drag_start(self, job_id: str, event):
        self._drag_job_id = job_id

    def _drag_motion(self, event):
        if not self._drag_job_id:
            return
        # Find which slot the cursor is over
        y = self._canvas.canvasy(event.y_root - self._canvas.winfo_rooty())
        idx = self._find_insert_index(y)
        if idx != self._drag_target_idx:
            self._drag_target_idx = idx
            self._show_indicator(idx)

    def _drag_release(self, event):
        if not self._drag_job_id:
            return
        job_id = self._drag_job_id
        target_idx = self._drag_target_idx
        self._drag_job_id = None
        self._drag_target_idx = -1
        self._hide_indicator()
        if target_idx >= 0:
            self._on_reorder(job_id, target_idx)

    def _find_insert_index(self, canvas_y: float) -> int:
        """Return the card index before which we should insert."""
        for i, jid in enumerate(self._job_order):
            card = self._cards.get(jid)
            if not card:
                continue
            card_y = card.winfo_y()
            card_h = card.winfo_height()
            if canvas_y < card_y + card_h / 2:
                return i
        return len(self._job_order)

    def _show_indicator(self, idx: int):
        self._hide_indicator()
        C = self._colors
        self._indicator = _DropIndicator(self._inner, C.get("accent", "#007acc"))
        # Position before card at idx
        cards_list = [self._cards.get(jid) for jid in self._job_order
                      if jid in self._cards]
        if idx < len(cards_list) and cards_list[idx]:
            cards_list[idx].pack_configure(before=self._indicator)
        self._indicator.pack(fill=tk.X, padx=6)

    def _hide_indicator(self):
        if self._indicator:
            self._indicator.destroy()
            self._indicator = None

    # ── Scroll / resize ────────────────────────────────────────────────

    def _on_inner_configure(self, _e=None):
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
        card_y   = card.winfo_y()
        card_h   = card.winfo_height()
        canvas_h = self._canvas.winfo_height()
        total_h  = self._inner.winfo_height()
        if total_h <= canvas_h:
            return
        frac_top = card_y / total_h
        frac_bot = (card_y + card_h) / total_h
        cur_top, cur_bot = self._canvas.yview()
        if frac_top < cur_top:
            self._canvas.yview_moveto(frac_top)
        elif frac_bot > cur_bot:
            self._canvas.yview_moveto(frac_bot - (cur_bot - cur_top))
