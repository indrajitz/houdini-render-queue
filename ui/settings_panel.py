"""
ui/settings_panel.py — Job settings editor.

New features vs v1:
  • "Scan ROPs" button — runs hython on the .hip and populates the ROP combobox
  • Selecting a ROP auto-fills frame start/end/step and shows the ROP's output path
  • Output path section: shows native ROP path (read-only) + optional override dir
  • Clean section-based layout
"""

import os
import threading
import tkinter as tk
from tkinter import filedialog, ttk
from typing import Callable, List, Optional

from queue_manager import RenderJob


class SettingsPanel(ttk.Frame):

    def __init__(self, parent, on_change: Optional[Callable] = None,
                 colors: dict = None, **kwargs):
        super().__init__(parent, style="Panel.TFrame", **kwargs)
        self._on_change    = on_change or (lambda: None)
        self._colors       = colors or {}
        self._job: Optional[RenderJob] = None
        self._vars: dict   = {}
        self._suppress     = False
        self._rop_list: List[dict] = []   # last scan results

        self._duplicate_callback: Optional[Callable[[RenderJob], None]] = None
        self._reset_callback: Optional[Callable[[str], None]] = None

        self._build()

    # ── Build ──────────────────────────────────────────────────────────

    def _build(self):
        C = self._colors
        panel_bg = C.get("panel", "#252526")

        self.columnconfigure(0, weight=1)

        # Section header
        hdr = tk.Frame(self, bg=panel_bg)
        hdr.grid(row=0, column=0, sticky=tk.EW)
        tk.Label(
            hdr, text="JOB SETTINGS",
            bg=panel_bg, fg=C.get("text_dim", "#858585"),
            font=("Segoe UI", 8, "bold"),
        ).pack(side=tk.LEFT, padx=10, pady=(8, 4))

        # Placeholder
        self._placeholder = tk.Label(
            self,
            text="Select a job to edit its settings\nor add a new one from the toolbar.",
            bg=panel_bg, fg=C.get("text_dim", "#555"),
            font=("Segoe UI", 10), justify=tk.CENTER,
        )
        self._placeholder.grid(row=1, column=0, padx=20, pady=40)

        # Scrollable form container
        self._form_outer = tk.Frame(self, bg=panel_bg)
        self._form_canvas = tk.Canvas(
            self._form_outer,
            bg=panel_bg, highlightthickness=0, bd=0,
        )
        self._form_scroll = ttk.Scrollbar(
            self._form_outer, orient=tk.VERTICAL,
            command=self._form_canvas.yview,
        )
        self._form_canvas.configure(yscrollcommand=self._form_scroll.set)
        self._form_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._form_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self._form = tk.Frame(self._form_canvas, bg=panel_bg)
        self._form_win = self._form_canvas.create_window(
            (0, 0), window=self._form, anchor=tk.NW)
        self._form.bind("<Configure>", self._on_form_configure)
        self._form_canvas.bind("<Configure>", self._on_canvas_configure)
        self._form_canvas.bind("<MouseWheel>", self._on_mousewheel)
        self._form_canvas.bind("<Button-4>",   self._on_mousewheel)
        self._form_canvas.bind("<Button-5>",   self._on_mousewheel)

        self._build_form(self._form)

    def _section(self, parent, text: str):
        C = self._colors
        f = tk.Frame(parent, bg=C.get("panel", "#252526"))
        f.pack(fill=tk.X, padx=8, pady=(10, 2))
        tk.Label(
            f, text=text.upper(),
            bg=C.get("panel", "#252526"),
            fg=C.get("text_dim", "#858585"),
            font=("Segoe UI", 7, "bold"),
        ).pack(side=tk.LEFT)
        tk.Frame(f, height=1, bg=C.get("border", "#3e3e42")).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 0), pady=6)

    def _field_row(self, parent, label: str):
        C = self._colors
        row = tk.Frame(parent, bg=C.get("panel", "#252526"))
        row.pack(fill=tk.X, padx=8, pady=2)
        tk.Label(
            row, text=label,
            bg=C.get("panel", "#252526"),
            fg=C.get("text_dim", "#858585"),
            font=("Segoe UI", 8),
            width=12, anchor=tk.E,
        ).pack(side=tk.LEFT, padx=(0, 6))
        return row

    def _build_form(self, frm):
        C = self._colors
        panel_bg = C.get("panel", "#252526")

        # ── Label ──────────────────────────────────────────────────────
        self._section(frm, "Job")
        row = self._field_row(frm, "Label")
        self._vars["label"] = tk.StringVar()
        e = ttk.Entry(row, textvariable=self._vars["label"])
        e.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._vars["label"].trace_add("write", lambda *_: self._changed("label"))

        # ── Hip file ───────────────────────────────────────────────────
        self._section(frm, "Project File")

        row = self._field_row(frm, "Hip File")
        self._vars["hip_file"] = tk.StringVar()
        ttk.Entry(row, textvariable=self._vars["hip_file"]).pack(
            side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(row, text="…", width=3, style="Small.TButton",
                   command=self._browse_hip).pack(side=tk.LEFT, padx=(3, 0))
        self._vars["hip_file"].trace_add("write", lambda *_: self._changed("hip_file"))

        # ── ROP ────────────────────────────────────────────────────────
        self._section(frm, "Output Driver (ROP)")

        # Scan controls
        scan_row = tk.Frame(frm, bg=panel_bg)
        scan_row.pack(fill=tk.X, padx=8, pady=(2, 4))

        self._scan_btn = ttk.Button(
            scan_row, text="⟳  Scan ROPs",
            style="Small.TButton",
            command=self._scan_rops,
        )
        self._scan_btn.pack(side=tk.LEFT)
        self._scan_status = tk.Label(
            scan_row, text="",
            bg=panel_bg, fg=C.get("text_dim", "#858585"),
            font=("Segoe UI", 8),
        )
        self._scan_status.pack(side=tk.LEFT, padx=8)

        # ROP combobox
        row = self._field_row(frm, "ROP")
        self._vars["rop_path"] = tk.StringVar()
        self._rop_combo = ttk.Combobox(
            row,
            textvariable=self._vars["rop_path"],
            state="normal",
        )
        self._rop_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._rop_combo.bind("<<ComboboxSelected>>", self._rop_selected)
        self._vars["rop_path"].trace_add("write", lambda *_: self._changed("rop_path"))

        # ── Frame range ────────────────────────────────────────────────
        self._section(frm, "Frame Range")

        frames_row = self._field_row(frm, "Range")
        self._vars["frame_start"] = tk.IntVar(value=1)
        self._vars["frame_end"]   = tk.IntVar(value=100)
        self._vars["frame_step"]  = tk.IntVar(value=1)

        tk.Label(frames_row, text="Start", bg=panel_bg,
                 fg=C.get("text_dim", "#858585"),
                 font=("Segoe UI", 8)).pack(side=tk.LEFT)
        ttk.Spinbox(frames_row, textvariable=self._vars["frame_start"],
                    from_=0, to=99999, width=6).pack(side=tk.LEFT, padx=(3, 8))
        tk.Label(frames_row, text="End", bg=panel_bg,
                 fg=C.get("text_dim", "#858585"),
                 font=("Segoe UI", 8)).pack(side=tk.LEFT)
        ttk.Spinbox(frames_row, textvariable=self._vars["frame_end"],
                    from_=0, to=99999, width=6).pack(side=tk.LEFT, padx=(3, 8))
        tk.Label(frames_row, text="Step", bg=panel_bg,
                 fg=C.get("text_dim", "#858585"),
                 font=("Segoe UI", 8)).pack(side=tk.LEFT)
        ttk.Spinbox(frames_row, textvariable=self._vars["frame_step"],
                    from_=1, to=1000, width=5).pack(side=tk.LEFT, padx=(3, 0))

        for key in ("frame_start", "frame_end", "frame_step"):
            self._vars[key].trace_add("write", lambda *_, k=key: self._changed(k))

        # Frame count label
        self._lbl_frame_count = tk.Label(
            frm, text="",
            bg=panel_bg, fg=C.get("accent", "#007acc"),
            font=("Segoe UI", 8),
        )
        self._lbl_frame_count.pack(anchor=tk.W, padx=(8 + 12*6 + 12, 0))

        # ── Output ────────────────────────────────────────────────────
        self._section(frm, "Output")

        # ROP native output path (read-only info)
        rop_out_row = self._field_row(frm, "ROP Output")
        self._lbl_rop_output = tk.Label(
            rop_out_row,
            text="—",
            bg=panel_bg,
            fg=C.get("accent", "#007acc"),
            font=("Courier New", 8),
            anchor=tk.W,
            wraplength=300,
            justify=tk.LEFT,
        )
        self._lbl_rop_output.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Override output directory
        row = self._field_row(frm, "Override Dir")
        self._vars["output_dir"] = tk.StringVar()
        ttk.Entry(row, textvariable=self._vars["output_dir"]).pack(
            side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(row, text="…", width=3, style="Small.TButton",
                   command=self._browse_output).pack(side=tk.LEFT, padx=(3, 0))
        self._vars["output_dir"].trace_add("write", lambda *_: self._changed("output_dir"))

        tk.Label(
            frm, text="Leave blank to use the path from the ROP",
            bg=panel_bg, fg=C.get("text_dim", "#555"),
            font=("Segoe UI", 7),
        ).pack(anchor=tk.W, padx=(8 + 12*6 + 12, 0))

        # ── Options ───────────────────────────────────────────────────
        self._section(frm, "Options")

        prio_row = self._field_row(frm, "Priority")
        self._vars["priority"] = tk.IntVar(value=50)
        self._slider = ttk.Scale(
            prio_row, from_=1, to=100, orient=tk.HORIZONTAL,
            variable=self._vars["priority"],
            command=self._priority_changed,
        )
        self._slider.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._lbl_prio_val = tk.Label(
            prio_row, text="50", width=3,
            bg=panel_bg, fg=C.get("text", "#d4d4d4"),
            font=("Segoe UI", 8),
        )
        self._lbl_prio_val.pack(side=tk.LEFT, padx=(4, 0))

        chk_row = self._field_row(frm, "")
        self._vars["enabled"] = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            chk_row, text="Enabled",
            variable=self._vars["enabled"],
            command=self._enabled_changed,
            style="TCheckbutton",
        ).pack(side=tk.LEFT)

        # ── Action buttons ────────────────────────────────────────────
        btn_row = tk.Frame(frm, bg=panel_bg)
        btn_row.pack(fill=tk.X, padx=8, pady=10)
        ttk.Button(btn_row, text="Reset Status",
                   command=self._reset_job,
                   style="Small.TButton").pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(btn_row, text="Duplicate Job",
                   command=self._duplicate_job,
                   style="Small.TButton").pack(side=tk.LEFT)

        # Padding at the bottom
        tk.Frame(frm, height=20, bg=panel_bg).pack()

    # ── Public API ─────────────────────────────────────────────────────

    def load_job(self, job: RenderJob):
        self._job = job
        self._placeholder.grid_remove()
        self._form_outer.grid(row=1, column=0, sticky=tk.NSEW, padx=0, pady=0)
        self.rowconfigure(1, weight=1)

        self._suppress = True
        self._vars["label"].set(job.label)
        self._vars["hip_file"].set(job.hip_file)
        self._vars["rop_path"].set(job.rop_path)
        self._vars["frame_start"].set(job.frame_start)
        self._vars["frame_end"].set(job.frame_end)
        self._vars["frame_step"].set(job.frame_step)
        self._vars["output_dir"].set(job.output_dir)
        self._vars["priority"].set(job.priority)
        self._lbl_prio_val.config(text=str(job.priority))
        self._vars["enabled"].set(job.enabled)
        self._lbl_rop_output.config(text=job.rop_output_path or "—")
        self._suppress = False

        self._update_frame_count()
        self._rop_list = []
        self._rop_combo["values"] = []

    def clear(self):
        self._job = None
        self._form_outer.grid_remove()
        self._placeholder.grid(row=1, column=0, padx=20, pady=40)

    def set_duplicate_callback(self, cb):
        self._duplicate_callback = cb

    def set_reset_callback(self, cb):
        self._reset_callback = cb

    def populate_rops(self, rops: List[dict]):
        """Called after a scan completes — populate the ROP combobox."""
        self._rop_list = rops
        values = [f"{r['path']}  [{r['type']}]" for r in rops]
        self._rop_combo["values"] = values
        self._scan_status.config(
            text=f"{len(rops)} ROP{'s' if len(rops) != 1 else ''} found",
            fg=self._colors.get("success", "#4ec9b0"),
        )

    # ── Internal ───────────────────────────────────────────────────────

    def _changed(self, key: str):
        if self._suppress or self._job is None:
            return
        try:
            val = self._vars[key].get()
        except (tk.TclError, ValueError):
            return

        try:
            setattr(self._job, key, val)
        except (AttributeError, TypeError):
            return

        if key == "hip_file":
            basename = os.path.basename(val)
            cur_lbl = self._vars["label"].get()
            if not cur_lbl or cur_lbl == os.path.basename(
                    self._job.hip_file or ""):
                self._suppress = True
                self._vars["label"].set(basename)
                self._job.label = basename
                self._suppress = False
            # Clear ROP list when hip changes
            self._rop_list = []
            self._rop_combo["values"] = []
            self._lbl_rop_output.config(text="—")
            self._scan_status.config(text="")

        if key in ("frame_start", "frame_end", "frame_step"):
            self._update_frame_count()

        self._on_change()

    def _priority_changed(self, val):
        if self._suppress or self._job is None:
            return
        try:
            ival = int(float(val))
        except ValueError:
            return
        self._job.priority = ival
        self._lbl_prio_val.config(text=str(ival))
        self._on_change()

    def _enabled_changed(self):
        if self._job is None:
            return
        self._job.enabled = self._vars["enabled"].get()
        self._on_change()

    def _rop_selected(self, _event=None):
        if self._job is None:
            return
        sel = self._rop_combo.get()
        # Find matching ROP dict
        rop = next(
            (r for r in self._rop_list if sel.startswith(r["path"])),
            None,
        )
        if not rop:
            return

        self._suppress = True
        # Update ROP path (strip the type label we appended)
        self._vars["rop_path"].set(rop["path"])
        self._job.rop_path = rop["path"]

        # Auto-fill frame range
        self._vars["frame_start"].set(rop["frame_start"])
        self._vars["frame_end"].set(rop["frame_end"])
        self._vars["frame_step"].set(rop["frame_step"])
        self._job.frame_start = rop["frame_start"]
        self._job.frame_end   = rop["frame_end"]
        self._job.frame_step  = rop["frame_step"]

        # Show ROP output path
        out_path = rop.get("output_path", "")
        self._job.rop_output_path = out_path
        self._lbl_rop_output.config(text=out_path or "—")

        self._suppress = False
        self._update_frame_count()
        self._on_change()

    def _update_frame_count(self):
        try:
            s = self._vars["frame_start"].get()
            e = self._vars["frame_end"].get()
            st = max(1, self._vars["frame_step"].get())
            count = max(0, len(range(s, e + 1, st)))
            self._lbl_frame_count.config(text=f"{count} frames total")
        except (tk.TclError, ValueError):
            pass

    def _scan_rops(self):
        if self._job is None:
            return
        hip = self._vars["hip_file"].get()
        if not hip or not os.path.isfile(hip):
            self._scan_status.config(
                text="No valid .hip file set",
                fg=self._colors.get("error", "#f44747"),
            )
            return

        self._scan_btn.config(state=tk.DISABLED)
        self._scan_status.config(
            text="Scanning…",
            fg=self._colors.get("text_dim", "#858585"),
        )

        # Run scan on background thread
        def run():
            try:
                from hip_scanner import scan_hip_rops
                from renderer import find_hython
                rops = scan_hip_rops(hip, hython=find_hython())
                self.after(0, lambda r=rops: self._scan_done(r, None))
            except Exception as exc:
                self.after(0, lambda e=exc: self._scan_done([], e))

        threading.Thread(target=run, daemon=True).start()

    def _scan_done(self, rops: list, error):
        self._scan_btn.config(state=tk.NORMAL)
        if error:
            self._scan_status.config(
                text=f"Error: {error}",
                fg=self._colors.get("error", "#f44747"),
            )
            return
        self.populate_rops(rops)
        if rops and self._job:
            # Auto-select if current ROP path matches one in the list
            current = self._job.rop_path
            match = next((r for r in rops if r["path"] == current), None)
            if not match and rops:
                match = rops[0]
            if match:
                self._suppress = True
                self._rop_combo.set(f"{match['path']}  [{match['type']}]")
                self._suppress = False
                self._rop_selected()

    def _browse_hip(self):
        path = filedialog.askopenfilename(
            title="Select Houdini Project",
            filetypes=[("Houdini Projects", "*.hip *.hipnc *.hiplc"),
                       ("All Files", "*.*")],
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

    # ── Scrollable form helpers ────────────────────────────────────────

    def _on_form_configure(self, _e=None):
        self._form_canvas.configure(scrollregion=self._form_canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self._form_canvas.itemconfig(self._form_win, width=event.width)

    def _on_mousewheel(self, event):
        if event.num == 4:
            self._form_canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self._form_canvas.yview_scroll(1, "units")
        else:
            self._form_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
