"""
ui/settings_panel.py — Right-panel job settings editor.

Edits the currently selected RenderJob in-place and commits changes
back to the QueueManager via a provided callback.
"""

import os
import tkinter as tk
from tkinter import ttk, filedialog
from typing import Callable, Optional

from queue_manager import RenderJob


class SettingsPanel(ttk.Frame):
    """
    Form-based editor for a single RenderJob.
    Call load_job(job) to populate, or clear() to show the placeholder.
    Call on_change to be notified of edits (for refreshing the queue card).
    """

    def __init__(self, parent, on_change: Optional[Callable] = None, **kwargs):
        super().__init__(parent, **kwargs)
        self._on_change = on_change or (lambda: None)
        self._job: Optional[RenderJob] = None
        self._vars: dict = {}
        self._build()

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(10, weight=1)

        # Title
        ttk.Label(self, text="JOB SETTINGS",
                  font=("Segoe UI", 9, "bold"), foreground="#6a8fb0").grid(
            row=0, column=0, sticky=tk.W, padx=8, pady=(6, 4))

        # Placeholder shown when nothing is selected
        self._placeholder = ttk.Label(
            self,
            text="Select a job in the queue\nto edit its settings.",
            foreground="#555555",
            font=("Segoe UI", 10),
            justify=tk.CENTER,
        )
        self._placeholder.grid(row=1, column=0, padx=20, pady=40)

        # Main form (hidden initially)
        self._form = ttk.Frame(self)
        self._form.columnconfigure(1, weight=1)
        self._build_form()

    def _build_form(self):
        frm = self._form
        row = 0

        def lbl(text, r, tooltip=None):
            l = ttk.Label(frm, text=text, anchor=tk.E, foreground="#a9b7c6")
            l.grid(row=r, column=0, sticky=tk.E, padx=(8, 4), pady=3)
            return l

        def entry(var_key, r, width=40, validator=None):
            v = tk.StringVar()
            self._vars[var_key] = v
            e = ttk.Entry(frm, textvariable=v, width=width)
            e.grid(row=r, column=1, sticky=tk.EW, padx=(0, 8), pady=3)
            v.trace_add("write", lambda *_: self._field_changed(var_key, validator))
            return e, v

        def spinbox(var_key, r, from_=1, to=9999, width=8):
            v = tk.IntVar()
            self._vars[var_key] = v
            sb = ttk.Spinbox(frm, textvariable=v, from_=from_, to=to, width=width)
            sb.grid(row=r, column=1, sticky=tk.W, padx=(0, 8), pady=3)
            v.trace_add("write", lambda *_: self._field_changed(var_key))
            return sb, v

        # ── Label ──────────────────────────────────────────────────────
        lbl("Label:", row)
        self._entry_label, self._vars["label"] = entry("label", row)
        row += 1

        # ── Hip file ───────────────────────────────────────────────────
        lbl("Hip File:", row)
        hip_frame = ttk.Frame(frm)
        hip_frame.grid(row=row, column=1, sticky=tk.EW, padx=(0, 8), pady=3)
        hip_frame.columnconfigure(0, weight=1)
        self._vars["hip_file"] = tk.StringVar()
        self._entry_hip = ttk.Entry(hip_frame, textvariable=self._vars["hip_file"])
        self._entry_hip.grid(row=0, column=0, sticky=tk.EW)
        ttk.Button(hip_frame, text="…", width=3,
                   command=self._browse_hip).grid(row=0, column=1, padx=(3, 0))
        self._vars["hip_file"].trace_add("write", lambda *_: self._field_changed("hip_file"))
        row += 1

        # ── ROP path ───────────────────────────────────────────────────
        lbl("ROP Path:", row)
        entry("rop_path", row)
        row += 1

        # ── Frame range ────────────────────────────────────────────────
        lbl("Frame Start:", row)
        spinbox("frame_start", row, from_=0)
        row += 1

        lbl("Frame End:", row)
        spinbox("frame_end", row, from_=0)
        row += 1

        lbl("Frame Step:", row)
        spinbox("frame_step", row, from_=1)
        row += 1

        # ── Output dir ─────────────────────────────────────────────────
        lbl("Output Dir:", row)
        out_frame = ttk.Frame(frm)
        out_frame.grid(row=row, column=1, sticky=tk.EW, padx=(0, 8), pady=3)
        out_frame.columnconfigure(0, weight=1)
        self._vars["output_dir"] = tk.StringVar()
        self._entry_out = ttk.Entry(out_frame, textvariable=self._vars["output_dir"])
        self._entry_out.grid(row=0, column=0, sticky=tk.EW)
        ttk.Button(out_frame, text="…", width=3,
                   command=self._browse_output).grid(row=0, column=1, padx=(3, 0))
        self._vars["output_dir"].trace_add("write", lambda *_: self._field_changed("output_dir"))
        row += 1

        # ── Priority ───────────────────────────────────────────────────
        lbl("Priority:", row)
        prio_frame = ttk.Frame(frm)
        prio_frame.grid(row=row, column=1, sticky=tk.EW, padx=(0, 8), pady=3)
        self._vars["priority"] = tk.IntVar()
        self._slider_priority = ttk.Scale(prio_frame, from_=1, to=100, orient=tk.HORIZONTAL,
                                          variable=self._vars["priority"],
                                          command=self._priority_changed)
        self._slider_priority.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._lbl_priority_val = ttk.Label(prio_frame, text="50", width=4)
        self._lbl_priority_val.pack(side=tk.LEFT, padx=(4, 0))
        row += 1

        ttk.Label(frm, text="(1 = highest, 100 = lowest)",
                  foreground="#666666",
                  font=("Segoe UI", 8)).grid(row=row, column=1, sticky=tk.W, padx=(0, 8))
        row += 1

        # ── Enabled ────────────────────────────────────────────────────
        self._vars["enabled"] = tk.BooleanVar()
        ttk.Checkbutton(frm, text="Enabled", variable=self._vars["enabled"],
                        command=self._enabled_changed).grid(
            row=row, column=1, sticky=tk.W, padx=(0, 8), pady=6)
        row += 1

        # ── Action buttons ─────────────────────────────────────────────
        btn_frame = ttk.Frame(frm)
        btn_frame.grid(row=row, column=0, columnspan=2, sticky=tk.EW, padx=8, pady=8)
        ttk.Button(btn_frame, text="Reset Job", command=self._reset_job).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="Duplicate Job", command=self._duplicate_job).pack(side=tk.LEFT, padx=4)

        self._duplicate_callback: Optional[Callable[[RenderJob], None]] = None
        self._reset_callback: Optional[Callable[[str], None]] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_job(self, job: RenderJob):
        self._job = job
        self._placeholder.grid_remove()
        self._form.grid(row=1, column=0, sticky=tk.NSEW, padx=0, pady=0)

        self._suppress = True
        self._vars["label"].set(job.label)
        self._vars["hip_file"].set(job.hip_file)
        self._vars["rop_path"].set(job.rop_path)
        self._vars["frame_start"].set(job.frame_start)
        self._vars["frame_end"].set(job.frame_end)
        self._vars["frame_step"].set(job.frame_step)
        self._vars["output_dir"].set(job.output_dir)
        self._vars["priority"].set(job.priority)
        self._lbl_priority_val.config(text=str(job.priority))
        self._vars["enabled"].set(job.enabled)
        self._suppress = False

    def clear(self):
        self._job = None
        self._form.grid_remove()
        self._placeholder.grid(row=1, column=0, padx=20, pady=40)

    def set_duplicate_callback(self, cb: Callable[[RenderJob], None]):
        self._duplicate_callback = cb

    def set_reset_callback(self, cb: Callable[[str], None]):
        self._reset_callback = cb

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    _suppress: bool = False

    def _field_changed(self, key: str, validator=None):
        if self._suppress or self._job is None:
            return
        val = self._vars[key].get()
        if validator:
            try:
                val = validator(val)
            except (ValueError, tk.TclError):
                return
        try:
            setattr(self._job, key, val)
        except (AttributeError, TypeError):
            return

        # Keep label in sync with hip filename if the label was auto-generated
        if key == "hip_file":
            current_label = self._vars["label"].get()
            basename = os.path.basename(val)
            if not current_label or current_label == os.path.basename(
                self._job.hip_file or ""
            ):
                self._suppress = True
                self._vars["label"].set(basename)
                self._job.label = basename
                self._suppress = False

        self._on_change()

    def _priority_changed(self, val):
        if self._suppress or self._job is None:
            return
        try:
            ival = int(float(val))
        except ValueError:
            return
        self._job.priority = ival
        self._lbl_priority_val.config(text=str(ival))
        self._on_change()

    def _enabled_changed(self):
        if self._job is None:
            return
        self._job.enabled = self._vars["enabled"].get()
        self._on_change()

    def _browse_hip(self):
        path = filedialog.askopenfilename(
            title="Select Houdini Project",
            filetypes=[("Houdini Projects", "*.hip *.hipnc *.hiplc"), ("All Files", "*.*")],
        )
        if path:
            self._vars["hip_file"].set(path)

    def _browse_output(self):
        path = filedialog.askdirectory(title="Select Output Directory")
        if path:
            self._vars["output_dir"].set(path)

    def _reset_job(self):
        if self._job and self._reset_callback:
            self._reset_callback(self._job.job_id)

    def _duplicate_job(self):
        if self._job and self._duplicate_callback:
            self._duplicate_callback(self._job)
