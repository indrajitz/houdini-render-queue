"""
ui/main_window.py — Top-level application frame.
"""

import copy
import os
import threading
import time
import tkinter as tk
import uuid
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import List, Optional

from queue_manager import QueueManager, RenderJob, JobStatus
from renderer import Renderer, find_hython
from ui.toolbar import Toolbar
from ui.queue_panel import QueuePanel
from ui.settings_panel import SettingsPanel
from ui.log_panel import LogPanel


class MainWindow(ttk.Frame):

    def __init__(self, parent: tk.Tk, dnd_available: bool = False,
                 colors: dict = None, **kwargs):
        super().__init__(parent, **kwargs)
        self._root          = parent
        self._dnd_available = dnd_available
        self._colors        = colors or {}
        self._qm            = QueueManager()
        self._renderer      = Renderer(self._qm)
        self._start_time: Optional[float] = None
        self._elapsed_id: Optional[str] = None
        self._pending: list = []
        self._pending_lock  = threading.Lock()
        self._build()
        self._wire_renderer()
        self._root.after(50, self._poll_ui)

    # ── Layout ─────────────────────────────────────────────────────────

    def _build(self):
        C = self._colors
        self.configure(style="TFrame")
        self.rowconfigure(2, weight=1)   # row 0=toolbar, 1=separator, 2=paned, 3=statusbar
        self.columnconfigure(0, weight=1)

        # Toolbar — row 0
        self._toolbar = Toolbar(
            self, colors=C,
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
        self._toolbar.grid(row=0, column=0, sticky=tk.EW)

        # Separator line — row 1
        tk.Frame(self, height=1, bg=C.get("border", "#3e3e42")).grid(
            row=1, column=0, sticky=tk.EW)

        # Main paned area — row 2
        self._paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        self._paned.grid(row=2, column=0, sticky=tk.NSEW)

        # Left — queue list
        self._queue_panel = QueuePanel(
            self._paned,
            on_select=self._on_job_selected,
            on_toggle=self._on_job_toggled,
            on_reorder=self._on_job_reorder,
            on_files_dropped=self._on_files_dropped,
            dnd_available=self._dnd_available,
            colors=C,
        )
        self._paned.add(self._queue_panel, weight=2)

        # Right — settings + log
        right_paned = ttk.PanedWindow(self._paned, orient=tk.VERTICAL)
        self._paned.add(right_paned, weight=3)

        self._settings_panel = SettingsPanel(
            right_paned,
            on_change=self._on_settings_changed,
            colors=C,
        )
        self._settings_panel.set_duplicate_callback(self._duplicate_job)
        self._settings_panel.set_reset_callback(self._reset_job)
        right_paned.add(self._settings_panel, weight=1)

        self._log_panel = LogPanel(right_paned, colors=C)
        right_paned.add(self._log_panel, weight=2)

        # Status bar — row 3
        self._status_bar = _StatusBar(self, colors=C)
        self._status_bar.grid(row=3, column=0, sticky=tk.EW)

    # ── Renderer callbacks (thread-safe) ───────────────────────────────

    def _wire_renderer(self):
        def push(fn):
            with self._pending_lock:
                self._pending.append(fn)

        self._renderer.on_job_started  = lambda j:    push(lambda j=j: self._ui_job_started(j))
        self._renderer.on_job_progress = lambda j:    push(lambda j=j: self._ui_job_progress(j))
        self._renderer.on_job_log      = lambda j, l: push(lambda j=j, l=l: self._ui_job_log(j, l))
        self._renderer.on_job_finished = lambda j:    push(lambda j=j: self._ui_job_finished(j))
        self._renderer.on_queue_finished = lambda:    push(self._ui_queue_finished)

    def _poll_ui(self):
        with self._pending_lock:
            cbs, self._pending = list(self._pending), []
        for cb in cbs:
            try:
                cb()
            except Exception:
                pass
        self._root.after(50, self._poll_ui)

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
        self._stop_elapsed()
        counts = self._qm.counts()
        self._status_bar.set_status(
            f"Queue finished — {counts['done']} done, {counts['failed']} failed")
        if counts["failed"]:
            messagebox.showwarning(
                "Queue Finished",
                f"{counts['failed']} job(s) failed. Check the log for details.")
        else:
            messagebox.showinfo(
                "Queue Finished",
                f"All {counts['done']} job(s) rendered successfully.")

    # ── Toolbar actions ────────────────────────────────────────────────

    def _add_job(self):
        paths = filedialog.askopenfilenames(
            title="Add Houdini Projects",
            filetypes=[("Houdini Projects", "*.hip *.hipnc *.hiplc"),
                       ("All Files", "*.*")],
        )
        self._add_hip_files(list(paths))

    def _on_files_dropped(self, paths: List[str]):
        self._add_hip_files(paths)

    def _add_hip_files(self, paths: List[str]):
        if not paths:
            return
        for path in paths:
            job = RenderJob(hip_file=path)
            self._qm.add_job(job)
        self._refresh_queue()
        last = self._qm.jobs[-1]
        self._queue_panel.select(last.job_id)
        self._settings_panel.load_job(last)

    def _remove_job(self):
        sel = self._queue_panel.selected_id
        if not sel:
            messagebox.showinfo("Remove Job", "No job selected.")
            return
        job = self._qm.get_job(sel)
        if job and job.status == JobStatus.RENDERING:
            messagebox.showwarning("Remove Job", "Cannot remove a job that is rendering.")
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

    def _on_job_reorder(self, job_id: str, target_idx: int):
        """Move job to the given target index (called from drag-reorder)."""
        jobs = self._qm.jobs
        src_idx = next((i for i, j in enumerate(jobs) if j.job_id == job_id), -1)
        if src_idx < 0:
            return
        # Move via repeated up/down swaps
        if target_idx > src_idx:
            for _ in range(target_idx - src_idx - 1):
                self._qm.move_down(job_id)
        else:
            for _ in range(src_idx - target_idx):
                self._qm.move_up(job_id)
        self._refresh_queue()
        self._queue_panel.select(job_id)

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

        hython = find_hython()
        if hython == "hython" and not _hython_on_path():
            if not self._ask_hython_path():
                return

        self._qm.reset_all()
        self._queue_panel.rebuild(self._qm.jobs)
        self._log_panel.clear()
        self._start_time = time.time()
        self._tick_elapsed()
        self._toolbar.set_rendering_state()
        self._status_bar.set_status("Starting render queue…")
        self._renderer.start()

    def _pause_render(self):
        if self._renderer.is_running and not self._renderer.is_paused:
            self._renderer.pause()
            self._toolbar.set_paused_state()
            self._status_bar.set_status("Paused — waiting for current frame…")

    def _stop_render(self):
        if not self._renderer.is_running:
            return
        if messagebox.askyesno("Stop Render",
                               "Stop the render queue? Current job will be marked Failed."):
            self._renderer.stop()
            self._toolbar.set_idle_state()
            self._stop_elapsed()
            self._queue_panel.refresh_all_cards()
            self._status_bar.set_status("Stopped by user.")

    def _skip_current(self):
        self._renderer.skip_current()
        self._queue_panel.refresh_all_cards()

    def _save_queue(self):
        path = filedialog.asksaveasfilename(
            title="Save Queue", defaultextension=".json",
            filetypes=[("JSON Queue", "*.json"), ("All Files", "*.*")],
            initialfile=os.path.basename(self._qm.current_file or "queue.json"),
        )
        if path:
            try:
                self._qm.save(path)
                self._status_bar.set_status(f"Saved: {path}")
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
                self._status_bar.set_status(f"Loaded: {path}")
            except Exception as exc:
                messagebox.showerror("Load Error", str(exc))

    def _clear_queue(self):
        if self._renderer.is_running:
            messagebox.showwarning("Clear Queue", "Cannot clear while rendering.")
            return
        if self._qm.jobs and messagebox.askyesno(
                "Clear Queue", "Remove all jobs from the queue?"):
            self._qm.clear()
            self._settings_panel.clear()
            self._log_panel.clear()
            self._refresh_queue()
            self._status_bar.set_status("Queue cleared.")

    # ── Job actions ────────────────────────────────────────────────────

    def _duplicate_job(self, source: RenderJob):
        new = RenderJob.from_dict(source.to_dict())
        new.job_id = str(uuid.uuid4())
        new.label  = f"{source.label} (copy)"
        self._qm.add_job(new)
        self._refresh_queue()
        self._queue_panel.select(new.job_id)
        self._settings_panel.load_job(new)

    def _reset_job(self, job_id: str):
        job = self._qm.get_job(job_id)
        if job:
            job.reset()
            self._queue_panel.refresh_card(job_id)
            self._log_panel.clear()

    # ── Selection ──────────────────────────────────────────────────────

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

    # ── Helpers ────────────────────────────────────────────────────────

    def _refresh_queue(self):
        self._queue_panel.rebuild(self._qm.jobs)
        self._status_bar.set_progress(self._qm.counts())

    def _ask_hython_path(self) -> bool:
        path = simpledialog.askstring(
            "hython Not Found",
            "hython was not found on PATH.\n\n"
            "Enter the full path to hython or set the HYTHON_PATH env var:",
            parent=self._root,
        )
        if path and os.path.isfile(path):
            self._renderer.set_hython(path)
            return True
        if path:
            messagebox.showerror("hython Not Found", f"File not found: {path}")
        return False

    def _tick_elapsed(self):
        if self._start_time is not None:
            elapsed = time.time() - self._start_time
            self._status_bar.set_elapsed(elapsed)
        self._elapsed_id = self._root.after(1000, self._tick_elapsed)

    def _stop_elapsed(self):
        if self._elapsed_id:
            self._root.after_cancel(self._elapsed_id)
            self._elapsed_id = None
        self._start_time = None

    def on_close(self):
        if self._renderer.is_running:
            if not messagebox.askyesno("Quit",
                                       "A render is in progress. Stop it and quit?"):
                return
            self._renderer.stop()
        self._root.destroy()


# ── Status bar ────────────────────────────────────────────────────────────────

class _StatusBar(ttk.Frame):
    def __init__(self, parent, colors: dict = None, **kwargs):
        super().__init__(parent, style="StatusBar.TFrame", **kwargs)
        C = colors or {}
        self._bg = C.get("bg", "#1e1e1e")
        self._build(C)

    def _build(self, C):
        tk.Frame(self, height=1, bg=C.get("border", "#3e3e42")).pack(fill=tk.X)

        inner = tk.Frame(self, bg=self._bg)
        inner.pack(fill=tk.X, padx=8, pady=3)

        self._lbl_status = tk.Label(
            inner, text="Ready",
            bg=self._bg, fg=C.get("text_dim", "#858585"),
            font=("Segoe UI", 8), anchor=tk.W,
        )
        self._lbl_status.pack(side=tk.LEFT)

        self._lbl_elapsed = tk.Label(
            inner, text="",
            bg=self._bg, fg=C.get("text_dim", "#858585"),
            font=("Segoe UI", 8), anchor=tk.E,
        )
        self._lbl_elapsed.pack(side=tk.RIGHT, padx=(8, 0))

        self._lbl_counts = tk.Label(
            inner, text="0 / 0 jobs",
            bg=self._bg, fg=C.get("text_dim", "#858585"),
            font=("Segoe UI", 8), anchor=tk.E,
        )
        self._lbl_counts.pack(side=tk.RIGHT, padx=8)

        self._progress = ttk.Progressbar(
            inner, orient=tk.HORIZONTAL, mode="determinate",
            style="blue.Horizontal.TProgressbar",
            maximum=100, value=0, length=160,
        )
        self._progress.pack(side=tk.RIGHT, padx=4)

    def set_status(self, msg: str):
        self._lbl_status.config(text=msg)

    def set_progress(self, counts: dict):
        total = counts["total"]
        done  = counts["done"] + counts["failed"] + counts["skipped"]
        pct   = int(done / total * 100) if total else 0
        self._progress.config(value=pct)
        self._lbl_counts.config(text=f"{done} / {total} jobs")

    def set_elapsed(self, seconds: float):
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        self._lbl_elapsed.config(text=f"{h:02d}:{m:02d}:{s:02d}")


def _hython_on_path() -> bool:
    import shutil
    return shutil.which("hython") is not None
