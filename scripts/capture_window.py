#!/usr/bin/env python3
"""Capture any macOS app window by name/owner and OCR it to text.

Fills the "observe a native app" gap (e.g. the Crew banking app, which is not a
browser window). Uses Quartz to find the on-screen window, screencapture to grab
just that window, and tesseract to read its text.

Usage:
  capture_window.py <owner_substring> [--ocr] [--out /tmp/x.png] [--list]

Examples:
  capture_window.py --list                 # list windows
  capture_window.py Crew --ocr             # capture + OCR the Crew window
  capture_window.py "Google Chrome" --out /tmp/chrome.png
"""

import argparse
import subprocess
import sys
import tempfile
import os

try:
    import Quartz
except ImportError:
    sys.exit("pyobjc-framework-Quartz not installed. Run: python3 -m pip install pyobjc-framework-Quartz")


def list_windows(min_size=100):
    wl = Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionOnScreenOnly, Quartz.kCGNullWindowID)
    out = []
    for w in wl:
        owner = w.get(Quartz.kCGWindowOwnerName) or ""
        name = w.get(Quartz.kCGWindowName) or ""
        b = w.get(Quartz.kCGWindowBounds, {})
        wpx = int(b.get("Width", 0)); hpx = int(b.get("Height", 0))
        if wpx > min_size and hpx > min_size and owner:
            out.append({
                "wid": w.get(Quartz.kCGWindowNumber),
                "owner": owner,
                "name": name,
                "width": wpx,
                "height": hpx,
            })
    return out


def find_window(owner_substring):
    windows = list_windows()
    matches = [w for w in windows if owner_substring.lower() in w["owner"].lower()]
    if matches:
        # Prefer the largest matching window (the app's main window).
        return max(matches, key=lambda w: w["width"] * w["height"])
    return None


def capture(window_id, out_path):
    # -l <id> captures that specific window; -x non-interactive; -o no shadow.
    subprocess.run(["screencapture", "-x", "-o", "-l", str(window_id), out_path], check=True)
    return out_path


def ocr(image_path):
    # tesseract stdout; best-effort.
    result = subprocess.run(
        ["tesseract", image_path, "stdout"], capture_output=True, text=True
    )
    return result.stdout.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("owner", nargs="?", help="window owner substring, e.g. 'Crew'")
    ap.add_argument("--list", action="store_true", help="list on-screen windows")
    ap.add_argument("--ocr", action="store_true", help="also OCR the captured image")
    ap.add_argument("--out", default=None, help="output image path")
    args = ap.parse_args()

    if args.list:
        for w in list_windows():
            print(f"  wid={w['wid']} owner='{w['owner']}' name='{w['name'][:30]}' {w['width']}x{w['height']}")
        return 0
    if not args.owner:
        ap.error("owner substring or --list is required")

    win = find_window(args.owner)
    if not win:
        print(f"no on-screen window matching '{args.owner}'", file=sys.stderr)
        return 1
    out = args.out or tempfile.mktemp(suffix=".png")
    capture(win["wid"], out)
    print(f"window: {win['owner']} ({win['name'][:30]}) {win['width']}x{win['height']}")
    print(f"image: {out}")
    if args.ocr:
        print("--- OCR ---")
        print(ocr(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
