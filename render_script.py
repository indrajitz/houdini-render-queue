"""
render_script.py — Invoked by hython per render job.

Usage:
    hython render_script.py --hip /path/to/file.hip --rop /out/redshift1 \
        --start 1 --end 100 --step 1 [--output-dir /path/to/output]
"""

import argparse
import os
import sys

# Output parameter names per ROP type (same map as scan_hip.py)
_OUTPUT_PARMS = {
    "ifd":              ["vm_picture"],
    "opengl":           ["picture"],
    "geometry":         ["sopoutput"],
    "alembic":          ["filename"],
    "comp":             ["copoutput"],
    "filecache":        ["file"],
    "filesave":         ["file"],
    "karma":            ["picture"],
    "karmarenderer":    ["picture"],
    "usdrender":        ["outputimage"],
    "usdrenderer":      ["outputimage"],
    "lop_usdrender":    ["outputimage"],
    "redshift_rop":     ["RS_outputFileNamePrefix"],
    "arnold":           ["ar_picture"],
    "arnold_rop":       ["ar_picture"],
    "htoa_rop":         ["ar_picture"],
    "octanerenderer":   ["houdini_outputimage", "outputimage", "filename"],
    "octane_rop":       ["houdini_outputimage", "outputimage", "filename"],
    "octane":           ["houdini_outputimage", "outputimage", "filename"],
    "OctaneRop":        ["houdini_outputimage", "outputimage", "filename"],
    "vray_renderer":    ["SettingsOutput_img_file", "filename"],
    "ris":              ["ri_display_0"],
    "prman":            ["ri_display_0"],
    "pbrt":             ["filename"],
}

_FALLBACK_PARMS = [
    "picture", "vm_picture", "outputimage", "filename",
    "sopoutput", "file", "RS_outputFileNamePrefix", "ar_picture",
    "houdini_outputimage",
]


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--hip",        required=True)
    p.add_argument("--rop",        required=True)
    p.add_argument("--start",      type=float, required=True)
    p.add_argument("--end",        type=float, required=True)
    p.add_argument("--step",       type=float, default=1.0)
    p.add_argument("--output-dir", default="")
    return p.parse_args()


def get_output_parm(rop_node):
    rop_type   = rop_node.type().name()
    candidates = _OUTPUT_PARMS.get(rop_type, []) + _FALLBACK_PARMS
    seen = set()
    for pname in candidates:
        if pname in seen:
            continue
        seen.add(pname)
        parm = rop_node.parm(pname)
        if parm is not None:
            return parm
    return None


def override_output_dir(rop_node, output_dir: str):
    if not output_dir:
        return
    output_dir = os.path.abspath(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    parm = get_output_parm(rop_node)
    if parm is None:
        print(f"[RenderQueue] WARNING: Could not find output parm on {rop_node.type().name()}, "
              "output directory override skipped.", flush=True)
        return

    current = parm.unexpandedString()
    basename = os.path.basename(current) if current else "render.$F4.exr"
    new_path = os.path.join(output_dir, basename).replace("\\", "/")
    parm.set(new_path)
    print(f"[RenderQueue] Output override: {parm.name()} = {new_path}", flush=True)


def render_job(args):
    import hou  # noqa: only available inside hython

    print(f"[RenderQueue] Loading: {args.hip}", flush=True)
    hou.hipFile.load(args.hip, suppress_save_prompt=True, ignore_load_warnings=False)
    print("[RenderQueue] Hip file loaded.", flush=True)

    rop_node = hou.node(args.rop)
    if rop_node is None:
        print(f"[RenderQueue] ERROR: ROP not found: {args.rop}", flush=True)
        sys.exit(1)

    rop_type = rop_node.type().name()
    print(f"[RenderQueue] ROP: {rop_node.path()}  type={rop_type}", flush=True)

    if args.output_dir:
        override_output_dir(rop_node, args.output_dir)

    start = int(args.start)
    end   = int(args.end)
    step  = max(1, int(args.step))
    frames = list(range(start, end + 1, step))
    total  = len(frames)
    print(f"[RenderQueue] Frames {start}–{end} step {step}  ({total} frames)", flush=True)

    # Show resolved output path
    parm = get_output_parm(rop_node)
    if parm:
        try:
            resolved = rop_node.parm(parm.name()).eval()
            print(f"[RenderQueue] Output: {parm.unexpandedString()}", flush=True)
        except Exception:
            pass

    # ── Render ────────────────────────────────────────────────────────────
    # We render frame-by-frame so we can emit progress markers.
    # Some third-party renderers (Redshift, Octane) support standard
    # hou.RopNode.render(); others may need special handling.

    rop_type_lower = rop_type.lower()

    for i, frame in enumerate(frames, 1):
        print(f"[RenderQueue] FRAME_START {frame}  ({i}/{total})", flush=True)
        try:
            _render_frame(rop_node, frame, rop_type_lower)
        except Exception as exc:
            print(f"[RenderQueue] ERROR frame {frame}: {exc}", flush=True)
            import traceback
            traceback.print_exc()
            sys.exit(1)
        print(f"[RenderQueue] FRAME_DONE {frame}  ({i}/{total})", flush=True)

    print("[RenderQueue] RENDER_COMPLETE", flush=True)


def _render_frame(rop_node, frame: int, rop_type_lower: str):
    """Render a single frame, using the best method for the ROP type."""
    import hou

    # Set the current frame
    hou.setFrame(frame)

    try:
        # Standard approach — works for Mantra, Redshift, Arnold, Karma, Octane, V-Ray
        rop_node.render(
            frame_range=(frame, frame, 1),
            ignore_inputs=False,
            verbose=True,
            output_progress=True,
        )
    except TypeError:
        # Older Houdini / some third-party renderers may not accept all kwargs
        try:
            rop_node.render(frame_range=(frame, frame, 1))
        except TypeError:
            rop_node.render()


def main():
    args = parse_args()

    if not os.path.isfile(args.hip):
        print(f"[RenderQueue] ERROR: Hip file not found: {args.hip}", flush=True)
        sys.exit(1)

    try:
        render_job(args)
    except SystemExit:
        raise
    except Exception as exc:
        print(f"[RenderQueue] ERROR: {exc}", flush=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
