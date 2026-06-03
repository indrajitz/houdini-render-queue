"""
scan_hip.py — Invoked by hython to introspect a .hip file.

Outputs a single JSON line to stdout containing all output ROPs
with their frame ranges and output paths.

Usage:
    hython scan_hip.py --hip /path/to/file.hip
"""

import argparse
import json
import sys

# Output parameter for each ROP type.  Values can be a list — first one found wins.
_OUTPUT_PARMS = {
    # Native Houdini
    "ifd":                  ["vm_picture"],
    "opengl":               ["picture"],
    "geometry":             ["sopoutput"],
    "alembic":              ["filename"],
    "comp":                 ["copoutput"],
    "filecache":            ["file"],
    "filesave":             ["file"],
    "channel":              ["chanfile"],
    "dop":                  ["dopoutput"],

    # Karma / USD
    "karma":                ["picture"],
    "karmarenderer":        ["picture"],
    "usdrender":            ["outputimage"],
    "usdrenderer":          ["outputimage"],
    "lop_usdrender":        ["outputimage"],

    # Redshift
    "redshift_rop":         ["RS_outputFileNamePrefix", "RS_outputFileNamePrefix"],

    # Arnold
    "arnold":               ["ar_picture"],
    "arnold_rop":           ["ar_picture"],
    "htoa_rop":             ["ar_picture"],

    # Octane
    "octanerenderer":       ["houdini_outputimage", "outputimage", "filename"],
    "octane_rop":           ["houdini_outputimage", "outputimage", "filename"],
    "octane":               ["houdini_outputimage", "outputimage", "filename"],
    "OctaneRop":            ["houdini_outputimage", "outputimage", "filename"],

    # V-Ray
    "vray_renderer":        ["SettingsOutput_img_file", "filename"],

    # RenderMan / PRMan
    "ris":                  ["ri_display_0", "filename"],
    "prman":                ["ri_display_0", "filename"],

    # PBRT
    "pbrt":                 ["filename"],

    # Maxwell
    "maxwell_render":       ["output_mxi_file", "filename"],

    # Renderman XPU
    "ipr_ris":              ["ri_display_0"],

    # Cycles
    "cycles":               ["picture", "filename"],
}

# Generic fallback parm names tried if type isn't in map
_FALLBACK_PARMS = [
    "picture", "vm_picture", "outputimage", "filename",
    "sopoutput", "file", "RS_outputFileNamePrefix",
    "ar_picture", "houdini_outputimage",
]


def _get_output_path(node) -> str:
    rop_type = node.type().name()
    candidates = _OUTPUT_PARMS.get(rop_type, []) + _FALLBACK_PARMS
    seen = set()
    for pname in candidates:
        if pname in seen:
            continue
        seen.add(pname)
        parm = node.parm(pname)
        if parm is not None:
            val = parm.unexpandedString()
            if val:
                return val
    return ""


def _get_frame_range(node):
    """Read the node's own frame range, falling back to scene globals."""
    frame_start, frame_end, frame_step = 1, 100, 1
    try:
        import hou
        trange = node.parm("trange")
        if trange is not None and int(trange.eval()) > 0:
            f1 = node.parm("f1")
            f2 = node.parm("f2")
            f3 = node.parm("f3")
            if f1:
                frame_start = int(f1.eval())
            if f2:
                frame_end = int(f2.eval())
            if f3:
                frame_step = max(1, int(f3.eval()))
        else:
            # Fall back to scene playback range
            frame_start = int(hou.playbar.playbackRange()[0])
            frame_end   = int(hou.playbar.playbackRange()[1])
    except Exception:
        pass
    return frame_start, frame_end, frame_step


def scan_rop(node) -> dict:
    try:
        rop_type  = node.type().name()
        fs, fe, fstep = _get_frame_range(node)
        return {
            "path":        node.path(),
            "type":        rop_type,
            "label":       node.name(),
            "frame_start": fs,
            "frame_end":   fe,
            "frame_step":  fstep,
            "output_path": _get_output_path(node),
        }
    except Exception:
        return {}


def _is_rop(node) -> bool:
    """True if the node is a render output driver (ROP)."""
    try:
        return node.type().category().name() == "Driver"
    except Exception:
        return False


def collect_rops(context_node) -> list:
    rops = []
    if context_node is None:
        return rops
    for node in context_node.children():
        if _is_rop(node):
            info = scan_rop(node)
            if info:
                rops.append(info)
        # Recurse into subnets / ropnets
        if node.type().name() in ("subnet", "ropnet"):
            rops.extend(collect_rops(node))
    return rops


def main():
    parser = argparse.ArgumentParser(description="Scan Houdini .hip for ROPs")
    parser.add_argument("--hip", required=True)
    args = parser.parse_args()

    import hou  # noqa: only available inside hython

    hou.hipFile.load(args.hip, suppress_save_prompt=True, ignore_load_warnings=True)

    rops = []

    # Primary: /out context
    rops.extend(collect_rops(hou.node("/out")))

    # Solaris/USD: /stage
    rops.extend(collect_rops(hou.node("/stage")))

    # Remove duplicates by path
    seen_paths = set()
    unique = []
    for r in rops:
        if r.get("path") not in seen_paths:
            seen_paths.add(r["path"])
            unique.append(r)

    print(json.dumps({"rops": unique}), flush=True)


if __name__ == "__main__":
    main()
