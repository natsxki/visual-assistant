"""
ScreenGuide — transparent overlay + prompt bar
macOS-compatible, uses tkinter for the overlay window.
"""

import tkinter as tk
import threading
import json
from capture import capture_active_window
from ai_engine import query_ai_for_steps

from PIL import Image
import base64
import io
from vision import extract_text_regions, find_best_match


# ── colour palette ──────────────────────────────────────────────
OVERLAY_BG   = "#000000"      # will be made transparent
ARROW_COLOR  = "#FF3B5C"
LABEL_BG     = "#FF3B5C"
LABEL_FG     = "#FFFFFF"
STEP_DONE    = "#00E5A0"

BAR_BG       = "#0D0D0D"
BAR_BORDER   = "#2A2A2A"
BAR_INPUT_BG = "#1A1A1A"
BAR_FG       = "#F0F0F0"
BAR_HINT     = "#555555"
ACCENT       = "#FF3B5C"


# ── helpers ─────────────────────────────────────────────────────
def draw_arrow(canvas, x1, y1, x2, y2, color=ARROW_COLOR, width=3):
    """Draw a line with an arrowhead."""
    canvas.create_line(
        x1, y1, x2, y2,
        fill=color, width=width,
        arrow=tk.LAST,
        arrowshape=(18, 22, 7),
        smooth=True,
    )


def draw_highlight(canvas, x, y, w, h, label, step_n, done=False):
    """Highlight a region with a rounded rect and step badge."""
    color = STEP_DONE if done else ARROW_COLOR
    # dashed rect
    canvas.create_rectangle(
        x, y, x + w, y + h,
        outline=color, width=2, dash=(8, 4),
    )
    # badge
    bx, by = x, y - 26
    badge_text = f"  {step_n}. {label}  "
    canvas.create_rectangle(bx, by, bx + len(badge_text) * 7 + 6, by + 22,
                            fill=color, outline="")
    canvas.create_text(bx + 4, by + 11, text=badge_text,
                       fill=LABEL_FG, font=("Menlo", 11, "bold"), anchor="w")


# ── overlay window ───────────────────────────────────────────────
class OverlayWindow:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.steps = []
        self.current_step = 0

        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()

        # Fullscreen transparent canvas window
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.geometry(f"{sw}x{sh}+0+0")
        self.win.attributes("-topmost", True)
        self.win.attributes("-transparentcolor", OVERLAY_BG)
        self.win.config(bg=OVERLAY_BG)

        # Make it click-through on macOS via wm_attributes
        # (tkinter doesn't expose NSWindow directly, so we layer a canvas
        #  that only intercepts the Next / Clear buttons we draw ourselves)
        self.canvas = tk.Canvas(
            self.win, bg=OVERLAY_BG,
            highlightthickness=0, bd=0,
            width=sw, height=sh,
        )
        self.canvas.pack(fill="both", expand=True)

        # Navigation buttons (bottom-right corner, above the prompt bar)
        btn_y = sh - 90
        self._btn_next = tk.Button(
            self.win, text="Next step →",
            command=self.next_step,
            bg=ACCENT, fg="white",
            font=("Menlo", 12, "bold"),
            relief="flat", padx=14, pady=6, cursor="hand2",
        )
        self._btn_next.place(x=sw - 160, y=btn_y)

        self._btn_clear = tk.Button(
            self.win, text="✕ Clear",
            command=self.clear,
            bg="#222", fg="#aaa",
            font=("Menlo", 11),
            relief="flat", padx=10, pady=6, cursor="hand2",
        )
        self._btn_clear.place(x=sw - 260, y=btn_y)

        self._hide_nav()

    # ── public API ───────────────────────────────────────────────
    def show_steps(self, steps: list):
        """Receive parsed step list from AI engine and start rendering."""
        self.steps = steps
        self.current_step = 0
        self._render_current()

    def next_step(self):
        if self.current_step < len(self.steps) - 1:
            self.current_step += 1
            self._render_current()
        else:
            self.clear()

    def clear(self):
        self.canvas.delete("all")
        self.steps = []
        self._hide_nav()

    # ── private ──────────────────────────────────────────────────
    def _render_current(self):
        self.canvas.delete("all")
        step = self.steps[self.current_step]
        kind   = step.get("kind", "highlight")
        label  = step.get("label", "")
        n      = self.current_step + 1

        if kind == "highlight":
            r = step["region"]               # {x, y, w, h}
            draw_highlight(self.canvas, r["x"], r["y"], r["w"], r["h"], label, n)

        elif kind == "arrow":
            f, t = step["from"], step["to"]  # {x, y}
            draw_arrow(self.canvas, f["x"], f["y"], t["x"], t["y"])
            # label near arrowhead
            self.canvas.create_text(
                t["x"] + 14, t["y"],
                text=f"{n}. {label}",
                fill=LABEL_FG, font=("Menlo", 12, "bold"), anchor="w",
            )

        elif kind == "arrow+highlight":
            r = step["region"]
            f, t = step["from"], step["to"]
            draw_arrow(self.canvas, f["x"], f["y"], t["x"], t["y"])
            draw_highlight(self.canvas, r["x"], r["y"], r["w"], r["h"], label, n)

        # step counter top-left
        total = len(self.steps)
        self.canvas.create_text(
            24, 24,
            text=f"Step {n} / {total}",
            fill=ARROW_COLOR, font=("Menlo", 13, "bold"), anchor="w",
        )

        self._show_nav()

    def _show_nav(self):
        self._btn_next.lift()
        self._btn_clear.lift()

    def _hide_nav(self):
        # keep buttons around but update label
        if self.steps:
            self._btn_next.config(text="✓ Done")
        else:
            self._btn_next.config(text="Next step →")


# ── prompt bar ───────────────────────────────────────────────────
class PromptBar:
    def __init__(self, root: tk.Tk, overlay: OverlayWindow):
        self.root    = root
        self.overlay = overlay
        self.loading = False

        sw = root.winfo_screenwidth()
        bar_h = 64

        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.geometry(f"{sw}x{bar_h}+0+{root.winfo_screenheight() - bar_h}")
        self.win.attributes("-topmost", True)
        self.win.config(bg=BAR_BG)

        # top border line
        tk.Frame(self.win, bg=BAR_BORDER, height=1).pack(fill="x")

        frame = tk.Frame(self.win, bg=BAR_BG, padx=16, pady=10)
        frame.pack(fill="both", expand=True)

        # icon
        tk.Label(frame, text="⬡", bg=BAR_BG, fg=ACCENT,
                 font=("Menlo", 20)).pack(side="left", padx=(0, 10))

        # text entry
        self.entry = tk.Entry(
            frame,
            bg=BAR_INPUT_BG, fg=BAR_FG,
            insertbackground=ACCENT,
            relief="flat", bd=0,
            font=("Menlo", 14),
        )
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.insert(0, "How do I …")
        self.entry.bind("<FocusIn>",  self._clear_hint)
        self.entry.bind("<FocusOut>", self._restore_hint)
        self.entry.bind("<Return>",   self._on_submit)

        # status label
        self.status = tk.Label(
            frame, text="", bg=BAR_BG, fg=BAR_HINT,
            font=("Menlo", 11),
        )
        self.status.pack(side="right", padx=(10, 0))

        # send button
        tk.Button(
            frame, text="Ask  ⏎",
            command=self._on_submit,
            bg=ACCENT, fg="white",
            font=("Menlo", 12, "bold"),
            relief="flat", padx=12, pady=2, cursor="hand2",
        ).pack(side="right", padx=(10, 0))

    # ── events ────────────────────────────────────────────────────
    def _clear_hint(self, _):
        if self.entry.get() == "How do I …":
            self.entry.delete(0, tk.END)
            self.entry.config(fg=BAR_FG)

    def _restore_hint(self, _):
        if not self.entry.get():
            self.entry.insert(0, "How do I …")
            self.entry.config(fg=BAR_HINT)

    def _on_submit(self, _=None):
        question = self.entry.get().strip()
        if not question or question == "How do I …" or self.loading:
            return

        self.loading = True
        self.status.config(text="Capturing screen…", fg=BAR_HINT)
        self.overlay.clear()

        # run in background so UI stays responsive
        threading.Thread(target=self._run_query, args=(question,), daemon=True).start()

    def _run_query(self, question: str):
        try:
            screenshot_b64, app_name = capture_active_window()

            # Decode image for OCR
            img_bytes = base64.b64decode(screenshot_b64)
            pil_img = Image.open(io.BytesIO(img_bytes))

            # Extract UI text regions
            regions = extract_text_regions(pil_img)

            self.status.config(text="Asking AI…")
            steps = query_ai_for_steps(question, screenshot_b64, app_name)

            # Convert AI steps → real coordinates
            converted_steps = []

            for step in steps:
                target = step.get("target", "")
                match = find_best_match(target, regions)

                if match:
                    converted_steps.append({
                        "kind": "highlight",
                        "label": step["label"],
                        "region": {
                            "x": match["x"],
                            "y": match["y"],
                            "w": match["w"],
                            "h": match["h"]
                        }
                    })

            self.root.after(0, lambda: self._on_result(converted_steps))
        except Exception as e:
            self.root.after(0, lambda: self._on_error(str(e)))

    def _on_result(self, steps):
        self.loading = False
        if steps:
            self.status.config(text=f"{len(steps)} steps  ✓", fg=STEP_DONE)
            self.overlay.show_steps(steps)
        else:
            self.status.config(text="No steps returned", fg=ARROW_COLOR)

    def _on_error(self, msg):
        self.loading = False
        self.status.config(text=f"Error: {msg[:60]}", fg=ARROW_COLOR)


# ── entry point ──────────────────────────────────────────────────
def main():
    root = tk.Tk()
    root.withdraw()          # hide the root window; we use Toplevels only

    overlay = OverlayWindow(root)
    bar     = PromptBar(root, overlay)

    root.mainloop()


if __name__ == "__main__":
    main()