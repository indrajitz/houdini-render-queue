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


def scan_rop(node):
    try:
        rop_type = node.type().name()

        # Frame range — read from node's trange parm
        frame_start, frame_end, frame_step = 1, 100, 1
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

        # Output path — check type-specific parms, then generic fallbacks
        output_parm_map = {
            "ifd":               "vm_picture",
            "opengl":            "picture",
            "arnold":            "ar_picture",
            "karma":             "picture",
            "karmarenderer":     "picture",
            "ris":               "ri_display_0",
            "redshift_rop":      "RS_outputFileNamePrefix",
            "geometry":          "sopoutput",
            "alembic":           "filename",
            "comp":              "copoutput",
            "filecache":         "file",
            "filesave":          "file",
            "usdrender":         "outputimage",
            "usdrenderer":       "outputimage",
            "pbrt":              "filename",
            "vray_renderer":     "SettingsOutput_img_file",
        }
        output_path = ""
        pname = output_parm_map.get(rop_type)
        if pname:
            parm = node.parm(pname)
            if parm:
                output_path = parm.unexpandedString()
        if not output_path:
            for fallback in ("picture", "vm_picture", "sopoutput", "filename",
                             "outputimage", "file", "copoutput"):
                parm = node.parm(fallback)
                if parm:
                    output_path = parm.unexpandedString()
                    break

        return {
            "path":        node.path(),
            "type":        rop_type,
            "label":       node.name(),
            "frame_start": frame_start,
            "frame_end":   frame_end,
            "frame_step":  frame_step,
            "output_path": output_path,
        }
    except Exception as exc:
        return None


def collect_rops(root):
    rops = []
    for node in root.children():
        # Skip subnet-like nodes but recurse into them
        cat = node.type().category().name()
        if cat == "Driver":
            info = scan_rop(node)
            if info:
                rops.append(info)
        # Recurse into subnet ROPs
        if node.type().name() in ("subnet", "ropnet"):
            rops.extend(collect_rops(node))
    return rops


def main():
    parser = argparse.ArgumentParser(description="Scan Houdini .hip for ROPs")
    parser.add_argument("--hip", required=True, help="Path to .hip file")
    args = parser.parse_args()

    import hou  # noqa: only available inside hython

    hou.hipFile.load(args.hip, suppress_save_prompt=True, ignore_load_warnings=True)

    rops = []

    out = hou.node("/out")
    if out:
        rops.extend(collect_rops(out))

    # Also scan /stage for Solaris/USD render nodes
    stage = hou.node("/stage")
    if stage:
        try:
            import hou
            for node in stage.allSubChildren():
                if node.type().category().name() == "Driver":
                    info = scan_rop(node)
                    if info:
                        rops.append(info)
        except Exception:
            pass

    print(json.dumps({"rops": rops}), flush=True)


if __name__ == "__main__":
    main()
