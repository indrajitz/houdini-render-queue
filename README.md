# Houdini Render Queue

A Cinema 4D–style render queue for Houdini, built with Python and tkinter (zero third-party dependencies).

Queue multiple `.hip` / `.hipnc` projects, configure output drivers, frame ranges, and render them sequentially — with real-time log output and per-job progress tracking.

---

## Requirements

| Requirement | Notes |
|---|---|
| Python 3.8+ | tkinter must be included (standard on Windows/macOS; see below for Linux) |
| Houdini 18.5+ | `hython` must be on `PATH` or configured via `HYTHON_PATH` |

### Linux — install tkinter

```bash
# Debian / Ubuntu
sudo apt install python3-tk

# Fedora / RHEL
sudo dnf install python3-tkinter
```

### No extra pip packages needed

All dependencies are Python standard library only (`tkinter`, `subprocess`, `threading`, `json`, `uuid`, `dataclasses`).

---

## Installation

```bash
git clone <repo-url> houdini-render-queue
cd houdini-render-queue
```

That's it. No virtual environment or `pip install` required.

---

## Running

```bash
python main.py
```

Or, if your system has multiple Python versions:

```bash
python3 main.py
```

### Configuring hython

The app searches for `hython` in this order:

1. `HYTHON_PATH` environment variable (full path to `hython`)
2. System `PATH`
3. Common installation directories:
   - **Windows:** `C:\Program Files\Side Effects Software\Houdini*\bin\hython.exe`
   - **macOS:** `/Applications/Houdini/Houdini*/…/bin/hython`
   - **Linux:** `/opt/hfs*/bin/hython`, `~/hfs*/bin/hython`

If `hython` cannot be found automatically you will be prompted to enter the full path when you click **Start**.

```bash
# Recommended: set the env var before launching
export HYTHON_PATH=/opt/hfs20.5.332/bin/hython
python main.py
```

---

## Usage

### Adding jobs

1. Click **➕ Add Job** in the toolbar (or use **File › Add Job**).
2. Select one or more `.hip` / `.hipnc` files. Each file becomes a separate job.
3. Each job is added to the queue with default settings.

### Configuring a job

Select a job in the left panel. The **Job Settings** editor appears on the right:

| Field | Description |
|---|---|
| **Label** | Friendly display name (auto-filled from filename) |
| **Hip File** | Path to the `.hip` / `.hipnc` project |
| **ROP Path** | Houdini node path for the output driver, e.g. `/out/mantra1` |
| **Frame Start / End / Step** | Frame range to render |
| **Output Dir** | Optional — overrides the ROP's output path directory |
| **Priority** | 1 (highest) to 100 (lowest). Jobs are processed lowest-number-first |
| **Enabled** | Uncheck to skip this job without removing it |

### Rendering

| Button | Action |
|---|---|
| **▶ Start** | Begin processing the queue top-to-bottom (respecting priority) |
| **⏸ Pause** | Pause after the current frame finishes |
| **▶ Resume** | Resume a paused queue |
| **⏹ Stop** | Abort immediately; current job is marked **Failed** |
| **⏭ Skip** | Skip the currently rendering job (marks it **Skipped**) |

### Job statuses

| Status | Meaning |
|---|---|
| **Waiting** | Queued, not yet started |
| **Rendering** | Currently being processed |
| **Done** | Completed successfully |
| **Failed** | Exited with an error (check the log) |
| **Skipped** | Manually skipped by the user |

### Saving and loading queues

- **💾 Save Queue** — saves the current queue to a `.json` file
- **📂 Load Queue** — loads a previously saved `.json` queue
- **🗑 Clear Queue** — removes all jobs (prompts for confirmation)

Queue files store job configuration only (not runtime state like logs).

---

## Architecture

```
houdini-render-queue/
├── main.py               # Entry point — creates the Tk root and MainWindow
├── queue_manager.py      # RenderJob dataclass, QueueManager, JSON serialisation
├── renderer.py           # Background thread runner; calls hython via subprocess
├── render_script.py      # Script executed by hython per job
├── requirements.txt      # (empty — stdlib only)
└── ui/
    ├── __init__.py
    ├── main_window.py    # Top-level frame, wires all panels together
    ├── toolbar.py        # Toolbar buttons and state machine
    ├── queue_panel.py    # Scrollable job card list
    ├── settings_panel.py # Job settings editor form
    └── log_panel.py      # Live log output viewer
```

### Data flow

```
User clicks Start
    └─► MainWindow._start_render()
            └─► Renderer.start()  (spawns RendererThread)
                    └─► for each job: subprocess hython render_script.py
                            └─► stdout lines ──► on_job_log callback
                                                       └─► pending_ui_queue
                                                               └─► UI poll (every 50 ms)
                                                                       └─► LogPanel.append()
                                                                       └─► QueuePanel.refresh_card()
```

### render_script.py

The script run inside `hython` per job:

```
hython render_script.py \
  --hip  /path/to/project.hip \
  --rop  /out/mantra1 \
  --start 1 --end 100 --step 1 \
  [--output-dir /renders/shot01]
```

Progress is communicated back via stdout markers that `renderer.py` parses:

```
[RenderQueue] FRAME_START <n>
[RenderQueue] FRAME_DONE  <n>
[RenderQueue] RENDER_COMPLETE
```

---

## Tips

- **Multiple ROPs** — add the same `.hip` file multiple times with different ROP paths to render several passes in one queue run.
- **Priority** — lower number = higher priority. All jobs at priority 1 render before any at priority 50.
- **Output Dir override** — if set, the ROP's output filename is kept but its directory is replaced. Useful for redirecting renders to a different disk without modifying the hip file.
- **Re-rendering** — after a queue run, click **Reset Job** in the settings panel (or **▶ Start** again — all jobs are reset automatically at queue start).

---

## Troubleshooting

**`hython not found`**  
Set `HYTHON_PATH=/path/to/hython` in your environment before launching.

**Jobs immediately fail**  
Check the log panel. Common causes:
- Hip file path no longer valid
- ROP path does not exist in the scene (`/out/mantra1` vs `/obj/…`)
- Houdini licence not available

**tkinter not found (Linux)**  
```bash
sudo apt install python3-tk   # Debian/Ubuntu
```

**App looks unstyled / white on macOS**  
macOS dark mode may conflict with the custom colour scheme. You can remove the `_configure_styles()` call in `main.py` to use the system default theme.
