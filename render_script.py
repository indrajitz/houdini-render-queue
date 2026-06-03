"""
render_script.py — Invoked by hython per render job.

Usage:
    hython render_script.py --hip /path/to/file.hip --rop /out/mantra1 \
        --start 1 --end 100 --step 1 [--output-dir /path/to/output]
"""

import argparse
import sys
import os


def parse_args():
    parser = argparse.ArgumentParser(description="Houdini render script for render queue")
    parser.add_argument("--hip", required=True, help="Path to the .hip/.hipnc file")
    parser.add_argument("--rop", required=True, help="ROP node path (e.g. /out/mantra1)")
    parser.add_argument("--start", type=float, required=True, help="Start frame")
    parser.add_argument("--end", type=float, required=True, help="End frame")
    parser.add_argument("--step", type=float, default=1.0, help="Frame step")
    parser.add_argument("--output-dir", default="", help="Override output directory for the ROP")
    return parser.parse_args()


def get_output_parms(rop_node):
    """Return list of parameter names that control output file path for common ROPs."""
    rop_type = rop_node.type().name()
    parm_map = {
        "ifd": ["vm_picture"],          # Mantra
        "opengl": ["picture"],          # OpenGL
        "arnold": ["ar_picture"],       # Arnold
        "karma": ["picture"],           # Karma (USD)
        "ris": ["ri_display_0"],        # RenderMan
        "redshift_rop": ["RS_outputFileNamePrefix"],  # Redshift
        "geometry": ["sopoutput"],      # Geometry cache
        "alembic": ["filename"],        # Alembic
        "comp": ["copoutput"],          # Compositing
        "filecache": ["file"],          # File cache
        "filesave": ["file"],           # File save
    }
    return parm_map.get(rop_type, ["picture", "vm_picture", "sopoutput", "filename"])


def override_output_dir(rop_node, output_dir):
    """Override the ROP's output path to use the given directory."""
    if not output_dir:
        return

    output_dir = os.path.abspath(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    candidate_parms = get_output_parms(rop_node)

    for parm_name in candidate_parms:
        parm = rop_node.parm(parm_name)
        if parm is not None:
            current = parm.unexpandedString()
            if current:
                # Replace directory portion, keep filename/expression
                basename = os.path.basename(current)
                # Handle cases where the path has frame expressions like $F4
                new_path = os.path.join(output_dir, basename).replace("\\", "/")
                parm.set(new_path)
                print(f"[RenderQueue] Output path overridden: {parm_name} = {new_path}", flush=True)
            break


def render_job(args):
    import hou  # noqa: only available inside hython

    print(f"[RenderQueue] Loading hip file: {args.hip}", flush=True)
    hou.hipFile.load(args.hip, suppress_save_prompt=True, ignore_load_warnings=False)
    print(f"[RenderQueue] Hip file loaded.", flush=True)

    rop_node = hou.node(args.rop)
    if rop_node is None:
        print(f"[RenderQueue] ERROR: ROP node not found: {args.rop}", flush=True)
        sys.exit(1)

    print(f"[RenderQueue] Found ROP: {rop_node.path()} (type: {rop_node.type().name()})", flush=True)

    if args.output_dir:
        override_output_dir(rop_node, args.output_dir)

    # Build frame list
    start = int(args.start)
    end = int(args.end)
    step = max(1, int(args.step))
    frames = list(range(start, end + 1, step))
    total_frames = len(frames)

    print(f"[RenderQueue] Rendering frames {start}-{end} step {step} ({total_frames} frames)", flush=True)

    def frame_start_cb(kwargs):
        frame = int(kwargs.get("frame", 0))
        idx = frames.index(frame) + 1 if frame in frames else "?"
        print(f"[RenderQueue] FRAME_START {frame} ({idx}/{total_frames})", flush=True)

    def frame_end_cb(kwargs):
        frame = int(kwargs.get("frame", 0))
        idx = frames.index(frame) + 1 if frame in frames else "?"
        print(f"[RenderQueue] FRAME_DONE {frame} ({idx}/{total_frames})", flush=True)

    # Render using renderFrames for fine-grained control
    try:
        # Try rendering with callbacks for progress
        rop_node.render(
            frame_range=(start, end, step),
            ignore_inputs=False,
            method=hou.renderMethod.FrameByFrame,
            verbose=True,
            output_progress=True,
        )
    except TypeError:
        # Older Houdini versions may not accept all kwargs
        rop_node.render(frame_range=(start, end, step))

    print(f"[RenderQueue] RENDER_COMPLETE", flush=True)


def main():
    args = parse_args()

    # Validate file exists
    if not os.path.isfile(args.hip):
        print(f"[RenderQueue] ERROR: Hip file not found: {args.hip}", flush=True)
        sys.exit(1)

    try:
        render_job(args)
    except Exception as exc:
        print(f"[RenderQueue] ERROR: {exc}", flush=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
