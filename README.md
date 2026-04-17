# ScreenGuide 🔴
> AI-powered visual overlay tutorials — ask how to do anything in any app.

---

## Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Grant permissions (macOS)
ScreenGuide needs two macOS permissions:

| Permission | Where to grant |
|---|---|
| **Screen Recording** | System Settings → Privacy & Security → Screen Recording → add Terminal (or your IDE) |
| **Accessibility** | System Settings → Privacy & Security → Accessibility → add Terminal |

Both are needed: Screen Recording for the screenshot, Accessibility for reading the frontmost window position.

### 3. Set your API key
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

Add this to `~/.zshrc` to make it permanent.

---

## Run

```bash
python overlay.py
```

A slim dark bar appears at the bottom of your screen.

1. Switch to any creative app (Photoshop, Blender, Final Cut, Figma…).
2. Click inside the ScreenGuide bar and type your question, e.g.:
   - *How do I mask a layer?*
   - *Where is the node compositor?*
   - *How do I add a keyframe?*
3. Press **Enter** or click **Ask ⏎**.
4. Arrows and highlight boxes appear on top of your app.
5. Click **Next step →** to walk through each step.
6. Click **✕ Clear** to dismiss.

---

## Test without an API key (demo mode)

Edit `overlay.py`, find `_run_query`, and replace:
```python
steps = query_ai_for_steps(question, screenshot_b64, app_name)
```
with:
```python
from ai_engine import demo_steps
steps = demo_steps()
```

This renders three hard-coded steps so you can see the overlay working immediately.

---

## File structure

```
screenguide/
├── overlay.py        # Main app: overlay window + prompt bar (tkinter)
├── capture.py        # macOS screen capture + frontmost app detection
├── ai_engine.py      # Claude Vision API call + JSON step parser
├── requirements.txt
└── README.md
```

---

## Roadmap / next steps

| Feature | Approach |
|---|---|
| Per-pixel coordinate accuracy | Add a UI-element detector (Florence-2 / OWL-ViT) to ground the AI's region guesses |
| App-specific context | Inject known panel layouts per app into the system prompt |
| Animated arrows | Use `canvas.after()` to animate a moving dot along the arrow path |
| Step audio narration | Pipe label text through `say` (macOS built-in TTS) |
| C++ / Metal renderer | Replace tkinter canvas with a Metal-backed overlay for GPU-accelerated drawing |
| Hotkey activation | Use `pynput` to listen for a global hotkey (e.g. ⌥Space) without focus |
