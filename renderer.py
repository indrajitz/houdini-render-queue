"""
renderer.py — Subprocess runner that calls hython with render_script.py per job.

The Renderer runs on a dedicated thread.  It communicates with the UI through
callbacks so the tkinter main loop is never blocked.
"""

import os
import re
import shutil
import subprocess
import sys
import threading
import time
from typing import Callable, List, Optional

from queue_manager import QueueManager, RenderJob, JobStatus

# Regex patterns to parse render_script.py stdout
_RE_FRAME_DONE = re.compile(r"\[RenderQueue\] FRAME_DONE (\d+)")
_RE_FRAME_START = re.compile(r"\[RenderQueue\] FRAME_START (\d+)")
_RE_RENDER_COMPLETE = re.compile(r"\[RenderQueue\] RENDER_COMPLETE")


def find_hython() -> str:
    """Locate the hython executable.  Checks PATH, then common install dirs."""
    # Prefer explicit env override
    env_val = os.environ.get("HYTHON_PATH", "")
    if env_val and os.path.isfile(env_val):
        return env_val

    # Check PATH
    found = shutil.which("hython")
    if found:
        return found

    # Common Houdini installation paths
    candidates = []
    if sys.platform == "win32":
        import glob
        candidates = glob.glob(r"C:\Program Files\Side Effects Software\Houdini*\bin\hython.exe")
    elif sys.platform == "darwin":
        import glob
        candidates = glob.glob("/Applications/Houdini/Houdini*/Frameworks/Houdini.framework/Versions/Current/Resources/bin/hython")
    else:
        import glob
        candidates = (
            glob.glob("/opt/hfs*/bin/hython")
            + glob.glob("/usr/local/hfs*/bin/hython")
            + glob.glob(os.path.expanduser("~/hfs*/bin/hython"))
        )

    candidates = sorted(candidates, reverse=True)  # newest version first
    for c in candidates:
        if os.path.isfile(c):
            return c

    # Fallback — let subprocess raise FileNotFoundError with a clear message
    return "hython"


# Path to our render script, resolved relative to this file
_RENDER_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "render_script.py")


class Renderer:
    """
    Manages the render loop.

    Callbacks (all called from the renderer thread — callers must schedule UI
    updates via widget.after() or a thread-safe queue):

        on_job_started(job)
        on_job_progress(job)          -- frames_done / total_frames updated
        on_job_log(job, line)         -- new log line
        on_job_finished(job)          -- status set to Done/Failed/Skipped
        on_queue_finished()
    """

    def __init__(self, queue_manager: QueueManager):
        self._qm = queue_manager
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()           # not paused initially
        self._current_proc: Optional[subprocess.Popen] = None
        self._proc_lock = threading.Lock()

        # Callbacks — set before calling start()
        self.on_job_started: Optional[Callable[[RenderJob], None]] = None
        self.on_job_progress: Optional[Callable[[RenderJob], None]] = None
        self.on_job_log: Optional[Callable[[RenderJob, str], None]] = None
        self.on_job_finished: Optional[Callable[[RenderJob], None]] = None
        self.on_queue_finished: Optional[Callable[[], None]] = None

        self._hython: str = find_hython()

    # ------------------------------------------------------------------
    # Public control API
    # ------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def is_paused(self) -> bool:
        return not self._pause_event.is_set()

    def start(self) -> None:
        if self.is_running:
            return
        self._stop_event.clear()
        self._pause_event.set()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="RendererThread")
        self._thread.start()

    def pause(self) -> None:
        """Pause after the current frame finishes."""
        self._pause_event.clear()

    def resume(self) -> None:
        self._pause_event.set()

    def stop(self) -> None:
        """Signal the renderer to stop and kill the current subprocess."""
        self._stop_event.set()
        self._pause_event.set()       # unblock if paused
        self._kill_current_proc()

    def skip_current(self) -> None:
        """Mark the currently rendering job as Skipped and kill its process."""
        for job in self._qm.jobs:
            if job.status == JobStatus.RENDERING:
                job.status = JobStatus.SKIPPED
                break
        self._kill_current_proc()

    def set_hython(self, path: str) -> None:
        self._hython = path

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _kill_current_proc(self) -> None:
        with self._proc_lock:
            if self._current_proc and self._current_proc.poll() is None:
                try:
                    self._current_proc.terminate()
                except OSError:
                    pass

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            # Wait if paused
            self._pause_event.wait()
            if self._stop_event.is_set():
                break

            job = self._qm.next_waiting_job()
            if job is None:
                # Queue exhausted
                if self.on_queue_finished:
                    self.on_queue_finished()
                break

            self._render_job(job)

        # Ensure any remaining rendering job is marked as failed on stop
        for job in self._qm.jobs:
            if job.status == JobStatus.RENDERING:
                job.status = JobStatus.FAILED
                if self.on_job_finished:
                    self.on_job_finished(job)

    def _render_job(self, job: RenderJob) -> None:
        job.status = JobStatus.RENDERING
        job.progress = 0.0
        job.frames_done = 0
        job.total_frames = max(
            1,
            len(range(job.frame_start, job.frame_end + 1, max(1, job.frame_step))),
        )
        job.log = ""

        if self.on_job_started:
            self.on_job_started(job)

        cmd = [
            self._hython,
            _RENDER_SCRIPT,
            "--hip", job.hip_file,
            "--rop", job.rop_path,
            "--start", str(job.frame_start),
            "--end", str(job.frame_end),
            "--step", str(job.frame_step),
        ]
        if job.output_dir:
            cmd += ["--output-dir", job.output_dir]

        self._log(job, f"[RenderQueue] Command: {' '.join(cmd)}\n")

        env = os.environ.copy()

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env,
            )
        except FileNotFoundError:
            msg = (
                f"[RenderQueue] ERROR: hython not found at '{self._hython}'.\n"
                "Set HYTHON_PATH environment variable or configure it in the app.\n"
            )
            self._log(job, msg)
            job.status = JobStatus.FAILED
            if self.on_job_finished:
                self.on_job_finished(job)
            return

        with self._proc_lock:
            self._current_proc = proc

        # Stream stdout line by line
        for line in proc.stdout:
            if self._stop_event.is_set():
                break

            self._log(job, line)

            # Check if job was externally skipped
            if job.status == JobStatus.SKIPPED:
                break

            m_done = _RE_FRAME_DONE.search(line)
            if m_done:
                job.frames_done += 1
                job.progress = job.frames_done / job.total_frames
                if self.on_job_progress:
                    self.on_job_progress(job)
                # Check pause after each frame
                self._pause_event.wait()

        proc.wait()

        with self._proc_lock:
            self._current_proc = None

        # Determine final status only if not already set externally
        if job.status == JobStatus.RENDERING:
            if proc.returncode == 0:
                job.status = JobStatus.DONE
                job.progress = 1.0
                job.frames_done = job.total_frames
            else:
                job.status = JobStatus.FAILED

        if self.on_job_finished:
            self.on_job_finished(job)

    def _log(self, job: RenderJob, line: str) -> None:
        job.log += line
        if self.on_job_log:
            self.on_job_log(job, line)
