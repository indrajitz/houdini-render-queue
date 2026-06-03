"""
ui/main_window.py — Top-level application frame.

Layout:
  ┌──────────────────────────────────────────────────────┐
  │  Toolbar                                             │
  ├──────────────────────────────────────────────────────┤
  │  QueuePanel (left, ~40%)  │  Right panel (60%)       │
  │                           │  ┌─────────────────────┐ │
  │                           │  │  SettingsPanel      │ │
  │                           │  ├─────────────────────┤ │
  │                           │  │  LogPanel           │ │
  │                           │  └─────────────────────┘ │
  ├──────────────────────────────────────────────────────┤
  │  StatusBar                                           │
  └──────────────────────────────────────────────────────┘
"""

import copy
import os
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Optional

from queue_manager import QueueManager, RenderJob, JobStatus
from renderer import Renderer, find_hython
from ui.toolbar import Toolbar
from ui.queue_panel import QueuePanel
from ui.settings_panel import SettingsPanel
from ui.log_panel import LogPanel


class MainWindow(ttk.Frame):
    """Root application frame."""

    def __init__(self, parent: tk.Tk, **kwargs):
        super().__init__(parent, **kwargs)
        self._root = parent
        self._qm = QueueManager()
        self._renderer = Renderer(self._qm)
        self._start_time: Optional[float] = None
        self._elapsed_timer_id: Optional[str] = None
        self._pending_ui_queue: list = []   # thread-safe message list
        self._pending_lock = threading.Lock()
        self._build()
        self._wire_renderer()
        self._start_ui_poll()

    # ------------------------------------------------------------------
    # Layout construction
    # ------------------------------------------------------------------

    def _build(self):
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)

        # ── Toolbar ───────────────────────────────────────────────────
        self._toolbar = Toolbar(
            self,
            add_job=self._add_job,
            remove_job=self._remove_job,
            move_up=self._move_up,
            move_down=self._move_down,
            start=self._start_render,
            pause=self._pause_render,
            stop=self._stop_render,
            skip=self._skip_current,
            save_queue=self._save_queue,
            load_queue=self._load_queue,
            clear_queue=self._clear_queue,
        )
        self._toolbar.grid(row=0, column=0, sticky=tk.EW, padx=0, pady=0)

        ttk.Separator(self, orient=tk.HORIZONTAL).grid(row=0, column=0, sticky=tk.EW, pady=(40, 0))

        # ── Main paned area ───────────────────────────────────────────
        self._paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        self._paned.grid(row=1, column=0, sticky=tk.NSEW, padx=0, pady=(2, 0))

        # Left — queue list
        self._queue_panel = QueuePanel(
            self._paned,
            on_select=self._on_job_selected,
            on_toggle=self._on_job_toggled,
        )
        self._paned.add(self._queue_panel, weight=2)

        # Right — settings + log in a vertical paned window
        right_paned = ttk.PanedWindow(self._paned, orient=tk.VERTICAL)
        self._paned.add(right_paned, weight=3)

        self._settings_panel = SettingsPanel(
            right_paned,
            on_change=self._on_settings_changed,
        )
        self._settings_panel.set_duplicate_callback(self._duplicate_job)
        self._settings_panel.set_reset_callback(self._reset_job)
        right_paned.add(self._settings_panel, weight=1)

        self._log_panel = LogPanel(right_paned)
        right_paned.add(self._log_panel, weight=2)

        # ── Status bar ────────────────────────────────────────────────
        self._status_bar = _StatusBar(self)
        self._status_bar.grid(row=2, column=0, sticky=tk.EW)

    # ------------------------------------------------------------------
    # Renderer wiring
    # ------------------------------------------------------------------

    def _wire_renderer(self):
        """Connect renderer callbacks — they run on the renderer thread,
        so we push messages onto our pending queue and drain on the UI thread."""

        def push(fn):
            with self._pending_lock:
                self._pending_ui_queue.append(fn)

        def on_job_started(job):
            push(lambda j=job: self._ui_job_started(j))

        def on_job_progress(job):
            push(lambda j=job: self._ui_job_progress(j))

        def on_job_log(job, line):
            push(lambda j=job, l=line: self._ui_job_log(j, l))

        def on_job_finished(job):
            push(lambda j=job: self._ui_job_finished(j))

        def on_queue_finished():
            push(self._ui_queue_finished)

        self._renderer.on_job_started = on_job_started
        self._renderer.on_job_progress = on_job_progress
        self._renderer.on_job_log = on_job_log
        self._renderer.on_job_finished = on_job_finished
        self._renderer.on_queue_finished = on_queue_finished

    # ------------------------------------------------------------------
    # UI polling loop
    # ------------------------------------------------------------------

    def _start_ui_poll(self):
        self._poll_ui_queue()

    def _poll_ui_queue(self):
        with self._pending_lock:
            callbacks = list(self._pending_ui_queue)
            self._pending_ui_queue.clear()
        for cb in callbacks:
            try:
                cb()
            except Exception:
                pass
        self._root.after(50, self._poll_ui_queue)

    # ------------------------------------------------------------------
    # Renderer UI callbacks (called on UI thread via poll)
    # ------------------------------------------------------------------

    def _ui_job_started(self, job: RenderJob):
        self._queue_panel.refresh_card(job.job_id)
        self._queue_panel.select(job.job_id)
        if self._queue_panel.selected_id == job.job_id:
            self._log_panel.clear()
        self._status_bar.set_status(f"Rendering: {job.label}")

    def _ui_job_progress(self, job: RenderJob):
        self._queue_panel.refresh_card(job.job_id)
        self._status_bar.set_progress(self._qm.counts())

    def _ui_job_log(self, job: RenderJob, line: str):
        if self._queue_panel.selected_id == job.job_id:
            self._log_panel.append(line)

    def _ui_job_finished(self, job: RenderJob):
        self._queue_panel.refresh_card(job.job_id)
        self._status_bar.set_progress(self._qm.counts())

    def _ui_queue_finished(self):
        self._toolbar.set_idle_state()
        self._stop_elapsed_timer()
        counts = self._qm.counts()
        failed = counts["failed"]
        done = counts["done"]
        self._status_bar.set_status(
            f"Queue finished — {done} done, {failed} failed"
        )
        if failed:
            messagebox.showwarning(
                "Queue Finished",
                f"Render queue completed with {failed} failed job(s).\n"
                "Check the log for details.",
            )
        else:
            messagebox.showinfo("Queue Finished", f"All {done} job(s) rendered successfully.")

    # ------------------------------------------------------------------
    # Toolbar actions
    # ------------------------------------------------------------------

    def _add_job(self):
        paths = filedialog.askopenfilenames(
            title="Add Houdini Projects",
            filetypes=[("Houdini Projects", "*.hip *.hipnc *.hiplc"), ("All Files", "*.*")],
        )
        if not paths:
            return
        for path in paths:
            job = RenderJob(hip_file=path)
            self._qm.add_job(job)
        self._refresh_queue()
        if paths:
            last_job = self._qm.jobs[-1]
            self._queue_panel.select(last_job.job_id)
            self._settings_panel.load_job(last_job)

    def _remove_job(self):
        sel = self._queue_panel.selected_id
        if not sel:
            messagebox.showinfo("Remove Job", "No job selected.")
            return
        job = self._qm.get_job(sel)
        if job and job.status == JobStatus.RENDERING:
            messagebox.showwarning("Remove Job", "Cannot remove a job that is currently rendering.")
            return
        self._qm.remove_job(sel)
        self._settings_panel.clear()
        self._log_panel.clear()
        self._refresh_queue()

    def _move_up(self):
        sel = self._queue_panel.selected_id
        if sel:
            self._qm.move_up(sel)
            self._refresh_queue()
            self._queue_panel.select(sel)

    def _move_down(self):
        sel = self._queue_panel.selected_id
        if sel:
            self._qm.move_down(sel)
            self._refresh_queue()
            self._queue_panel.select(sel)

    def _start_render(self):
        if not self._qm.jobs:
            messagebox.showinfo("Start Render", "The queue is empty.")
            return

        if self._renderer.is_paused:
            self._renderer.resume()
            self._toolbar.set_resumed_state()
            self._status_bar.set_status("Resumed")
            return

        if self._renderer.is_running:
            return

        # Ask about hython if not found
        hython = find_hython()
        if hython == "hython" and not _hython_on_path():
            configured = self._ask_hython_path()
            if not configured:
                return

        self._qm.reset_all()
        self._queue_panel.rebuild(self._qm.jobs)
        self._log_panel.clear()

        self._start_time = time.time()
        self._start_elapsed_timer()
        self._toolbar.set_rendering_state()
        self._status_bar.set_status("Starting render queue…")

        self._renderer.start()

    def _pause_render(self):
        if self._renderer.is_running and not self._renderer.is_paused:
            self._renderer.pause()
            self._toolbar.set_paused_state()
            self._status_bar.set_status("Paused — waiting for current frame to finish…")

    def _stop_render(self):
        if not self._renderer.is_running:
            return
        if messagebox.askyesno("Stop Render", "Stop the render queue? The current job will be marked Failed."):
            self._renderer.stop()
            self._toolbar.set_idle_state()
            self._stop_elapsed_timer()
            self._queue_panel.refresh_all_cards()
            self._status_bar.set_status("Stopped by user.")

    def _skip_current(self):
        self._renderer.skip_current()
        self._queue_panel.refresh_all_cards()

    def _save_queue(self):
        path = filedialog.asksaveasfilename(
            title="Save Queue",
            defaultextension=".json",
            filetypes=[("JSON Queue", "*.json"), ("All Files", "*.*")],
            initialfile=os.path.basename(self._qm.current_file or "queue.json"),
        )
        if path:
            try:
                self._qm.save(path)
                self._status_bar.set_status(f"Queue saved: {path}")
            except Exception as exc:
                messagebox.showerror("Save Error", str(exc))

    def _load_queue(self):
        path = filedialog.askopenfilename(
            title="Load Queue",
            filetypes=[("JSON Queue", "*.json"), ("All Files", "*.*")],
        )
        if path:
            try:
                self._qm.load(path)
                self._settings_panel.clear()
                self._log_panel.clear()
                self._refresh_queue()
                self._status_bar.set_status(f"Queue loaded: {path}")
            except Exception as exc:
                messagebox.showerror("Load Error", str(exc))

    def _clear_queue(self):
        if self._renderer.is_running:
            messagebox.showwarning("Clear Queue", "Cannot clear while rendering.")
            return
        if self._qm.jobs and messagebox.askyesno("Clear Queue", "Remove all jobs from the queue?"):
            self._qm.clear()
            self._settings_panel.clear()
            self._log_panel.clear()
            self._refresh_queue()
            self._status_bar.set_status("Queue cleared.")

    # ------------------------------------------------------------------
    # Job-level actions
    # ------------------------------------------------------------------

    def _duplicate_job(self, source_job: RenderJob):
        new_job = RenderJob.from_dict(source_job.to_dict())
        import uuid
        new_job.job_id = str(uuid.uuid4())
        new_job.label = f"{source_job.label} (copy)"
        self._qm.add_job(new_job)
        self._refresh_queue()
        self._queue_panel.select(new_job.job_id)
        self._settings_panel.load_job(new_job)

    def _reset_job(self, job_id: str):
        job = self._qm.get_job(job_id)
        if job:
            job.reset()
            self._queue_panel.refresh_card(job_id)
            self._log_panel.clear()

    # ------------------------------------------------------------------
    # Selection / settings callbacks
    # ------------------------------------------------------------------

    def _on_job_selected(self, job_id: str):
        job = self._qm.get_job(job_id)
        if job:
            self._settings_panel.load_job(job)
            self._log_panel.set_job_log(job.log)
        else:
            self._settings_panel.clear()
            self._log_panel.clear()

    def _on_job_toggled(self, job_id: str):
        self._queue_panel.refresh_card(job_id)

    def _on_settings_changed(self):
        sel = self._queue_panel.selected_id
        if sel:
            self._queue_panel.refresh_card(sel)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _refresh_queue(self):
        self._queue_panel.rebuild(self._qm.jobs)
        self._status_bar.set_progress(self._qm.counts())

    def _ask_hython_path(self) -> bool:
        path = simpledialog.askstring(
            "hython Not Found",
            "hython was not found on PATH.\n\n"
            "Enter the full path to hython (or set the HYTHON_PATH env var):",
            parent=self._root,
        )
        if path and os.path.isfile(path):
            self._renderer.set_hython(path)
            return True
        if path:
            messagebox.showerror("hython Not Found", f"File not found: {path}")
        return False

    # ------------------------------------------------------------------
    # Elapsed time
    # ------------------------------------------------------------------

    def _start_elapsed_timer(self):
        self._stop_elapsed_timer()
        self._tick_elapsed()

    def _tick_elapsed(self):
        if self._start_time is not None:
            elapsed = time.time() - self._start_time
            self._status_bar.set_elapsed(elapsed)
        self._elapsed_timer_id = self._root.after(1000, self._tick_elapsed)

    def _stop_elapsed_timer(self):
        if self._elapsed_timer_id:
            self._root.after_cancel(self._elapsed_timer_id)
            self._elapsed_timer_id = None
        self._start_time = None

    # ------------------------------------------------------------------
    # Window close
    # ------------------------------------------------------------------

    def on_close(self):
        if self._renderer.is_running:
            if not messagebox.askyesno(
                "Quit",
                "A render is in progress. Stop it and quit?",
            ):
                return
            self._renderer.stop()
        self._root.destroy()


# ──────────────────────────────────────────────────────────────────────────────
# Status bar
# ──────────────────────────────────────────────────────────────────────────────

class _StatusBar(ttk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, style="StatusBar.TFrame", **kwargs)
        self._build()

    def _build(self):
        self.columnconfigure(1, weight=1)
        ttk.Separator(self, orient=tk.HORIZONTAL).grid(row=0, column=0, columnspan=4, sticky=tk.EW)

        self._lbl_status = ttk.Label(
            self, text="Ready", style="StatusBar.TLabel", width=45, anchor=tk.W
        )
        self._lbl_status.grid(row=1, column=0, padx=(8, 12), pady=3, sticky=tk.W)

        self._progress = ttk.Progressbar(
            self,
            orient=tk.HORIZONTAL,
            mode="determinate",
            style="blue.Horizontal.TProgressbar",
            maximum=100,
            value=0,
            length=200,
        )
        self._progress.grid(row=1, column=1, sticky=tk.EW, padx=4, pady=3)

        self._lbl_counts = ttk.Label(
            self, text="0 / 0 jobs", style="StatusBar.TLabel", width=15, anchor=tk.CENTER
        )
        self._lbl_counts.grid(row=1, column=2, padx=8, pady=3)

        self._lbl_elapsed = ttk.Label(
            self, text="", style="StatusBar.TLabel", width=12, anchor=tk.E
        )
        self._lbl_elapsed.grid(row=1, column=3, padx=(4, 8), pady=3, sticky=tk.E)

    def set_status(self, msg: str):
        self._lbl_status.config(text=msg)

    def set_progress(self, counts: dict):
        total = counts["total"]
        done = counts["done"] + counts["failed"] + counts["skipped"]
        pct = int(done / total * 100) if total else 0
        self._progress.config(value=pct)
        self._lbl_counts.config(text=f"{done} / {total} jobs")

    def set_elapsed(self, seconds: float):
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        self._lbl_elapsed.config(text=f"{h:02d}:{m:02d}:{s:02d}")


# ──────────────────────────────────────────────────────────────────────────────

def _hython_on_path() -> bool:
    import shutil
    return shutil.which("hython") is not None
