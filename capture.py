"""
capture.py — grab the frontmost window on macOS.

Strategy
--------
1. Use `screencapture` (built-in macOS CLI) to grab the whole display.
2. Use `osascript` to get the name of the frontmost application.
3. Return (base64_png, app_name) for the AI engine.

No third-party deps required — only stdlib + Pillow (for crop/encode).
Install Pillow once:  pip install Pillow
"""

import subprocess
import base64
import tempfile
import os
import json


# ── active app detection ─────────────────────────────────────────
def get_frontmost_app() -> tuple[str, dict]:
    """
    Returns (app_name, window_bounds) of the frontmost window.
    window_bounds = {"x": int, "y": int, "w": int, "h": int}
    Falls back to full-screen bounds if AppleScript fails.
    """
    script = """
    tell application "System Events"
        set frontApp to name of first application process whose frontmost is true
        set frontWindow to first window of (first process whose frontmost is true)
        set {x, y} to position of frontWindow
        set {w, h} to size of frontWindow
        return frontApp & "," & x & "," & y & "," & w & "," & h
    end tell
    """
    try:
        result = subprocess.check_output(
            ["osascript", "-e", script],
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).decode().strip()
        parts = result.split(",")
        app_name = parts[0].strip()
        x, y, w, h = int(parts[1]), int(parts[2]), int(parts[3]), int(parts[4])
        return app_name, {"x": x, "y": y, "w": w, "h": h}
    except Exception:
        # fallback: full screen
        size_script = 'tell application "Finder" to get bounds of window of desktop'
        try:
            out = subprocess.check_output(
                ["osascript", "-e", size_script], timeout=5
            ).decode().strip()
            # returns "0, 0, 2560, 1600" or similar
            coords = [int(v.strip()) for v in out.split(",")]
            return "Unknown", {"x": 0, "y": 0, "w": coords[2], "h": coords[3]}
        except Exception:
            return "Unknown", {"x": 0, "y": 0, "w": 1920, "h": 1080}


# ── screenshot ───────────────────────────────────────────────────
def capture_active_window() -> tuple[str, str]:
    """
    Captures the screen (or frontmost window region) as a PNG,
    encodes it to base64, and returns (base64_string, app_name).

    We capture the full display then crop to the window rect.
    This avoids permission issues with per-window capture on newer macOS.
    """
    from PIL import Image  # pip install Pillow

    app_name, bounds = get_frontmost_app()

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        tmp_path = f.name

    try:
        # -x = no sound, -t png = format
        subprocess.run(
            ["screencapture", "-x", "-t", "png", tmp_path],
            check=True, timeout=10,
        )

        img = Image.open(tmp_path)

        # Crop to window bounds if we got valid bounds
        sw, sh = img.size
        x = max(0, bounds["x"])
        y = max(0, bounds["y"])
        w = min(bounds["w"], sw - x)
        h = min(bounds["h"], sh - y)

        if w > 10 and h > 10:
            img = img.crop((x, y, x + w, y + h))

        # Resize if too large (keeps token cost down)
        max_dim = 1280
        ratio = min(max_dim / img.width, max_dim / img.height, 1.0)
        if ratio < 1.0:
            new_size = (int(img.width * ratio), int(img.height * ratio))
            img = img.resize(new_size, Image.LANCZOS)

        # Encode
        import io
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

        return b64, app_name

    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass