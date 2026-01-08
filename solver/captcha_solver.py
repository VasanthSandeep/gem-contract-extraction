"""
Advanced GeM CAPTCHA Solver
- Supports lowercase a-z + digits
- Multi-preprocessing
- Multi-PSM OCR
- Confidence voting
"""

import io
import cv2
import numpy as np
from PIL import Image, ImageOps, ImageFilter
import pytesseract
from collections import Counter

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

ALLOWED = "abcdefghijklmnopqrstuvwxyz0123456789"

# --------------------------------------------------
# IMAGE VARIANTS (KEY IMPROVEMENT)
# --------------------------------------------------
def generate_variants(img: Image.Image):
    variants = []

    gray = img.convert("L")
    variants.append(gray)

    # High contrast
    variants.append(ImageOps.autocontrast(gray, cutoff=1))

    # Sharpen
    variants.append(gray.filter(ImageFilter.SHARPEN))

    # Blur + threshold
    arr = np.array(gray)
    th = cv2.adaptiveThreshold(
        arr, 255,
        cv2.ADAPTIVE_THRESH_MEAN_C,
        cv2.THRESH_BINARY,
        31, 5
    )
    variants.append(Image.fromarray(th))

    # Inverted
    variants.append(ImageOps.invert(gray))

    return variants

# --------------------------------------------------
# OCR PASS
# --------------------------------------------------
def ocr_pass(img, psm):
    cfg = (
        f"--psm {psm} --oem 3 "
        f"-c tessedit_char_whitelist={ALLOWED}"
    )
    txt = pytesseract.image_to_string(img, config=cfg)
    return "".join(c for c in txt.lower() if c in ALLOWED)

# --------------------------------------------------
# VOTING LOGIC
# --------------------------------------------------
def smart_vote(results):
    if not results:
        return ""

    length_scores = Counter(len(r) for r in results if 4 <= len(r) <= 6)
    if not length_scores:
        return ""

    target_len = length_scores.most_common(1)[0][0]
    filtered = [r for r in results if len(r) == target_len]

    final = ""
    for i in range(target_len):
        chars = [r[i] for r in filtered if i < len(r)]
        if chars:
            final += Counter(chars).most_common(1)[0][0]

    return final

# --------------------------------------------------
# MAIN SOLVER
# --------------------------------------------------
def ensemble_solve(img_pil):
    if not isinstance(img_pil, Image.Image):
        img_pil = Image.open(io.BytesIO(img_pil))

    img_pil = img_pil.resize(
        (img_pil.width * 3, img_pil.height * 3),
        Image.Resampling.LANCZOS
    )

    results = []

    for variant in generate_variants(img_pil):
        for psm in [6, 7, 8, 10, 13]:
            try:
                txt = ocr_pass(variant, psm)
                if 4 <= len(txt) <= 6:
                    results.append(txt)
            except:
                pass

    final = smart_vote(results)
    confidence = min(0.95, 0.4 + 0.1 * len(results))

    return final, confidence