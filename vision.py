import cv2
import pytesseract
import numpy as np
from PIL import Image


def extract_text_regions(pil_image):
    """
    Returns list of:
    {
        "text": str,
        "x": int,
        "y": int,
        "w": int,
        "h": int
    }
    """

    img = np.array(pil_image)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)[1]

    data = pytesseract.image_to_data(gray, output_type=pytesseract.Output.DICT)

    results = []

    for i in range(len(data["text"])):
        text = data["text"][i].strip()

        if text and len(text) > 2:
            x = data["left"][i]
            y = data["top"][i]
            w = data["width"][i]
            h = data["height"][i]

            results.append({
                "text": text,
                "x": x,
                "y": y,
                "w": w,
                "h": h
            })

    return results

def find_best_match(target, regions):
    target = target.lower()

    best = None
    best_score = 0

    for r in regions:
        text = r["text"].lower()

        if target in text or text in target:
            score = len(text)

            if score > best_score:
                best = r
                best_score = score

    return best