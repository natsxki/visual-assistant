"""
ai_engine.py — sends screenshot + question to Gemini,
returns structured visual guidance steps.

Requires:
    pip install google-generativeai
"""

import os
import json
import re
import base64
import google.generativeai as genai


SYSTEM_PROMPT = SYSTEM_PROMPT = """
You are ScreenGuide, a UI tutor.

You will receive a screenshot and a question.

Return a JSON array of steps.

Each step must describe WHAT to interact with, not coordinates.

Format:

{
  "kind": "click",
  "label": "short step name",
  "target": "exact UI text or element name"
}

Rules:
- target must match visible UI text (e.g. "Layers", "File", "Opacity")
- no coordinates
- 2–6 steps
- return only JSON array
- if unsure return []
"""


def query_ai_for_steps(question: str, screenshot_b64: str, app_name: str) -> list:
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise EnvironmentError("GOOGLE_API_KEY not set")

    genai.configure(api_key=api_key)

    model = genai.GenerativeModel("gemini-1.5-pro")

    image_bytes = base64.b64decode(screenshot_b64)

    prompt = f"""
App: {app_name}
Question: {question}

Return the step array now.
"""

    response = model.generate_content([
        SYSTEM_PROMPT,
        prompt,
        {
            "mime_type": "image/png",
            "data": image_bytes
        }
    ])

    raw = response.text.strip()
    return _parse_steps(raw)


def _parse_steps(raw: str) -> list:
    clean = re.sub(r"```json|```", "", raw).strip()

    try:
        steps = json.loads(clean)
        if isinstance(steps, list):
            return steps
    except:
        pass

    match = re.search(r"\[.*\]", clean, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except:
            pass

    return []


def demo_steps() -> list:
    return [
        {
            "kind": "highlight",
            "label": "Open menu",
            "region": {"x": 20, "y": 20, "w": 220, "h": 28},
        },
        {
            "kind": "arrow",
            "label": "Click Layers",
            "from": {"x": 200, "y": 200},
            "to": {"x": 80, "y": 48},
        },
    ]