"""
ScreenGuide — transparent overlay + prompt bar
macOS-compatible, uses tkinter for the overlay window. (MVP version)
"""

import tkinter as tk
import threading
from capture import capture_active_window
from ai_engine import query_ai_for_steps

from PIL import Image
import base64
import io
from vision import extract_text_regions, find_best_match


# ── colour palette ──────────────────────────────────────────────
OVERLAY_BG   = "#000000"
ARROW_COLOR  = "#FF3B5C"
LABEL_FG     = "#FFFFFF"
STEP_DONE    = "#00E5A0"

BAR_BG       = "#0D0D0D"
BAR_BORDER   = "#2A2A2A"
BAR_HINT     = "#555555"
ACCENT       = "#FF3B5C"


# ── helpers ─────────────────────────────────────────────────────
def draw_arrow(canvas, x1, y1, x2, y2, color=ARROW_COLOR, width=3):
    canvas.create_line(
        x1, y1, x2, y2,
        fill=color,
        width=width,
        arrow=tk.LAST,
        arrowshape=(18, 22, 7),
        smooth=True,
    )


def draw_highlight(canvas, x, y, w, h, label, step_n):
    canvas.create_rectangle(
        x, y, x + w, y + h,
        outline=ARROW_COLOR,
        width=2,
        dash=(8, 4),
    )

    bx, by = x, y - 26
    badge_text = f"  {step_n}. {label}  "

    canvas.create_rectangle(
        bx,
        by,
        bx + len(badge_text) * 7 + 6,
        by + 22,
        fill=ARROW_COLOR,
        outline=""
    )

    canvas.create_text(
        bx + 4,
        by + 11,
        text=badge_text,
        fill=LABEL_FG,
        font=("Menlo", 11, "bold"),
        anchor="w"
    )


# ── overlay window ──────────────────────────────────────────────
class OverlayWindow:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.steps = []
        self.current_step = 0

        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()

        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.geometry(f"{sw}x{sh}+0+0")
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", 0.3)
        self.win.config(bg="white")

        self.canvas = tk.Canvas(
            self.win,
            bg="white",
            highlightthickness=0,
            bd=0,
            width=sw,
            height=sh,
        )
        self.canvas.pack(fill="both", expand=True)

        btn_y = sh - 120

        self._btn_next = tk.Button(
            self.win,
            text="Next step →",
            command=self.next_step,
            bg=ACCENT,
            fg="white",
            font=("Menlo", 12, "bold"),
            relief="flat",
            padx=14,
            pady=6,
        )
        self._btn_next.place(x=sw - 160, y=btn_y)

        self._btn_clear = tk.Button(
            self.win,
            text="✕ Clear",
            command=self.clear,
            bg="#222",
            fg="#aaa",
            font=("Menlo", 11),
            relief="flat",
            padx=10,
            pady=6,
        )
        self._btn_clear.place(x=sw - 260, y=btn_y)

        self.win.withdraw()

    def show_steps(self, steps):
        self.steps = steps
        self.current_step = 0
        self.win.deiconify()
        self.win.lift()
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
        self.win.withdraw()

    def _render_current(self):
        self.canvas.delete("all")

        step = self.steps[self.current_step]
        label = step["label"]
        region = step["region"]

        draw_highlight(
            self.canvas,
            region["x"],
            region["y"],
            region["w"],
            region["h"],
            label,
            self.current_step + 1
        )

        total = len(self.steps)
        self.canvas.create_text(
            24,
            24,
            text=f"Step {self.current_step+1} / {total}",
            fill=ARROW_COLOR,
            font=("Menlo", 13, "bold"),
            anchor="w"
        )


# ── prompt bar ──────────────────────────────────────────────────
class PromptBar:
    def __init__(self, root: tk.Tk, overlay: OverlayWindow):
        self.root = root
        self.overlay = overlay
        self.loading = False

        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()

        bar_w = 900
        bar_h = 64
        x = (sw - bar_w) // 2
        y = sh - bar_h - 120

        self.win = tk.Toplevel(root)

        # IMPORTANT: no overrideredirect here
        self.win.geometry(f"{bar_w}x{bar_h}+{x}+{y}")
        self.win.attributes("-topmost", True)
        self.win.config(bg=BAR_BG)
        self.win.lift()
        self.win.focus_force()

        tk.Frame(self.win, bg=BAR_BORDER, height=1).pack(fill="x")

        frame = tk.Frame(self.win, bg=BAR_BG, padx=16, pady=10)
        frame.pack(fill="both", expand=True)

        tk.Label(
            frame,
            text="⬡",
            bg=BAR_BG,
            fg=ACCENT,
            font=("Menlo", 20)
        ).pack(side="left", padx=(0, 10))

        self.entry = tk.Entry(
            frame,
            bg="white",
            fg="black",
            insertbackground="black",
            relief="flat",
            bd=0,
            font=("Menlo", 14),
        )
        self.entry.pack(side="left", fill="x", expand=True)

        self.entry.insert(0, "How do I …")
        self.entry.config(fg="gray")

        self.entry.bind("<FocusIn>", self._clear_hint)
        self.entry.bind("<FocusOut>", self._restore_hint)
        self.entry.bind("<Return>", self._on_submit)

        self.win.after(200, lambda: self.entry.focus_force())

        self.status = tk.Label(
            frame,
            text="",
            bg=BAR_BG,
            fg=BAR_HINT,
            font=("Menlo", 11),
        )
        self.status.pack(side="right", padx=(10, 0))

        tk.Button(
            frame,
            text="Ask ⏎",
            command=self._on_submit,
            bg=ACCENT,
            fg="white",
            font=("Menlo", 12, "bold"),
            relief="flat",
            padx=12,
            pady=2,
        ).pack(side="right", padx=(10, 0))

    def _clear_hint(self, _):
        if self.entry.get() == "How do I …":
            self.entry.delete(0, tk.END)
            self.entry.config(fg="black")

    def _restore_hint(self, _):
        if not self.entry.get():
            self.entry.insert(0, "How do I …")
            self.entry.config(fg="gray")

    def _on_submit(self, _=None):
        question = self.entry.get().strip()
        if not question or question == "How do I …" or self.loading:
            return

        self.loading = True
        self.status.config(text="Capturing screen…")
        self.overlay.clear()

        threading.Thread(
            target=self._run_query,
            args=(question,),
            daemon=True
        ).start()

    def _run_query(self, question):
        try:
            screenshot_b64, app_name = capture_active_window()

            img_bytes = base64.b64decode(screenshot_b64)
            pil_img = Image.open(io.BytesIO(img_bytes))

            regions = extract_text_regions(pil_img)

            self.status.config(text="Asking AI…")
            steps = query_ai_for_steps(question, screenshot_b64, app_name)

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
                            "h": match["h"],
                        }
                    })

            self.root.after(0, lambda: self._on_result(converted_steps))

        except Exception as e:
            self.root.after(0, lambda: self._on_error(str(e)))

    def _on_result(self, steps):
        self.loading = False
        if steps:
            self.status.config(text=f"{len(steps)} steps ✓", fg=STEP_DONE)
            self.overlay.show_steps(steps)
        else:
            self.status.config(text="No steps returned", fg=ARROW_COLOR)

    def _on_error(self, msg):
        self.loading = False
        self.status.config(text=f"Error: {msg[:50]}", fg=ARROW_COLOR)


# ── main ────────────────────────────────────────────────────────
def main():
    root = tk.Tk()
    root.withdraw()

    overlay = OverlayWindow(root)
    PromptBar(root, overlay)

    root.mainloop()


if __name__ == "__main__":
    main()