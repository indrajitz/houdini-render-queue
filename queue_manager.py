"""
queue_manager.py — Job data model, queue state, and JSON serialization.
"""

import json
import os
import uuid
from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import List, Optional


class JobStatus(str, Enum):
    WAITING = "Waiting"
    RENDERING = "Rendering"
    DONE = "Done"
    FAILED = "Failed"
    SKIPPED = "Skipped"


@dataclass
class RenderJob:
    """Represents a single render job in the queue."""

    job_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    hip_file: str = ""
    rop_path: str = "/out/mantra1"
    frame_start: int = 1
    frame_end: int = 100
    frame_step: int = 1
    output_dir: str = ""
    priority: int = 50          # 1 (highest) – 100 (lowest)
    enabled: bool = True
    label: str = ""             # Optional friendly name

    # Runtime state (not serialised to JSON)
    status: JobStatus = field(default=JobStatus.WAITING, compare=False)
    progress: float = field(default=0.0, compare=False)   # 0.0–1.0
    frames_done: int = field(default=0, compare=False)
    total_frames: int = field(default=0, compare=False)
    log: str = field(default="", compare=False)

    def __post_init__(self):
        if not self.label:
            self.label = os.path.basename(self.hip_file) if self.hip_file else "Untitled Job"
        self.total_frames = max(
            1,
            len(range(self.frame_start, self.frame_end + 1, max(1, self.frame_step))),
        )

    def reset(self):
        """Reset runtime state for re-rendering."""
        self.status = JobStatus.WAITING
        self.progress = 0.0
        self.frames_done = 0
        self.log = ""

    def to_dict(self) -> dict:
        """Serialise to dict (excludes runtime state)."""
        return {
            "job_id": self.job_id,
            "hip_file": self.hip_file,
            "rop_path": self.rop_path,
            "frame_start": self.frame_start,
            "frame_end": self.frame_end,
            "frame_step": self.frame_step,
            "output_dir": self.output_dir,
            "priority": self.priority,
            "enabled": self.enabled,
            "label": self.label,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RenderJob":
        allowed = {k for k in cls.__dataclass_fields__ if k not in
                   ("status", "progress", "frames_done", "total_frames", "log")}
        filtered = {k: v for k, v in data.items() if k in allowed}
        return cls(**filtered)


class QueueManager:
    """Manages an ordered list of RenderJob items."""

    def __init__(self):
        self._jobs: List[RenderJob] = []
        self._queue_file: Optional[str] = None

    # ------------------------------------------------------------------
    # Queue manipulation
    # ------------------------------------------------------------------

    @property
    def jobs(self) -> List[RenderJob]:
        return list(self._jobs)

    def add_job(self, job: RenderJob) -> None:
        self._jobs.append(job)

    def remove_job(self, job_id: str) -> bool:
        for i, job in enumerate(self._jobs):
            if job.job_id == job_id:
                del self._jobs[i]
                return True
        return False

    def get_job(self, job_id: str) -> Optional[RenderJob]:
        for job in self._jobs:
            if job.job_id == job_id:
                return job
        return None

    def move_up(self, job_id: str) -> bool:
        for i, job in enumerate(self._jobs):
            if job.job_id == job_id and i > 0:
                self._jobs[i], self._jobs[i - 1] = self._jobs[i - 1], self._jobs[i]
                return True
        return False

    def move_down(self, job_id: str) -> bool:
        for i, job in enumerate(self._jobs):
            if job.job_id == job_id and i < len(self._jobs) - 1:
                self._jobs[i], self._jobs[i + 1] = self._jobs[i + 1], self._jobs[i]
                return True
        return False

    def clear(self) -> None:
        self._jobs.clear()

    def reset_all(self) -> None:
        """Reset all jobs to Waiting status."""
        for job in self._jobs:
            job.reset()

    # ------------------------------------------------------------------
    # Iteration helpers
    # ------------------------------------------------------------------

    def next_waiting_job(self) -> Optional[RenderJob]:
        """Return first enabled Waiting job, sorted by priority then position."""
        candidates = [j for j in self._jobs if j.enabled and j.status == JobStatus.WAITING]
        if not candidates:
            return None
        return min(candidates, key=lambda j: (j.priority, self._jobs.index(j)))

    def all_done(self) -> bool:
        return all(
            j.status in (JobStatus.DONE, JobStatus.FAILED, JobStatus.SKIPPED) or not j.enabled
            for j in self._jobs
        )

    def counts(self) -> dict:
        total = len(self._jobs)
        done = sum(1 for j in self._jobs if j.status == JobStatus.DONE)
        failed = sum(1 for j in self._jobs if j.status == JobStatus.FAILED)
        skipped = sum(1 for j in self._jobs if j.status == JobStatus.SKIPPED)
        rendering = sum(1 for j in self._jobs if j.status == JobStatus.RENDERING)
        waiting = sum(1 for j in self._jobs if j.status == JobStatus.WAITING)
        return {
            "total": total,
            "done": done,
            "failed": failed,
            "skipped": skipped,
            "rendering": rendering,
            "waiting": waiting,
        }

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def save(self, path: str) -> None:
        data = {
            "version": 1,
            "jobs": [j.to_dict() for j in self._jobs],
        }
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        self._queue_file = path

    def load(self, path: str) -> None:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        self._jobs = [RenderJob.from_dict(d) for d in data.get("jobs", [])]
        self._queue_file = path

    @property
    def current_file(self) -> Optional[str]:
        return self._queue_file
