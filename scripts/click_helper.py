#!/usr/bin/env python3
"""Click a coordinate in the native Crew app by IMAGE coords (from a screenshot).

The Crew window is 288x545 pt at screen origin (WIN_X, WIN_Y); the read_image
capture is 576x1090 px (2x). This maps an image (px) coordinate to the screen
(pt) coordinate and clicks there via `cliclick`, so the agent can drive the app
the same way ChatGPT did — then run scripts/collect_crew_ops.py to capture the
GraphQL operation that fires.

Usage:
  click_helper.py --img 288,508           # click image px (288,508) = Save
  click_helper.py --img 288,508 --button right

Only performs mouse clicks (no keyboard). For text entry the app uses native
inputs that cliclick types via `cliclick t:` — see --type.
"""

import argparse
import subprocess
import sys

# Defaults (overridden by --win-x/--win-y or live introspection).
WIN_X = 301
WIN_Y = 108
WIN_W = 288   # window width pt
WIN_H = 545   # window height pt
IMG_W = 576   # capture width px (2x)
IMG_H = 1090  # capture height px (2x)


def img_to_screen(img_x: float, img_y: float):
    """Map an image-pixel coordinate to a macOS screen-point coordinate."""
    x = WIN_X + (img_x / IMG_W) * WIN_W
    y = WIN_Y + (img_y / IMG_H) * WIN_H
    return int(round(x)), int(round(y))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--img", required=True, help="image coord as 'x,y' in px")
    ap.add_argument("--button", default="left", choices=["left", "right", "c", "m"])
    ap.add_argument("--type", dest="text", default=None, help="text to type after (unused)")
    args = ap.parse_args()
    try:
        img_x, img_y = [float(v) for v in args.img.split(",")]
    except ValueError as exc:
        sys.exit(f"--img must be 'x,y': {exc}")
    sx, sy = img_to_screen(img_x, img_y)
    # cliclick tokens: c=click, dc=doubleclick, rt=right, cc=ctrl-click; button map
    token = {"left": "c", "right": "rt", "c": "cc", "m": "mc"}.get(args.button, "c")
    cmd = ["cliclick", f"{token}:{sx},{sy}"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit(f"cliclick failed: {result.stderr.strip()}")
    print(f"clicked img({img_x},{img_y}) -> screen({sx},{sy})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
