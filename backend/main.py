import base64
import hashlib
import io
import json
import logging
import os
import re
import unicodedata
import uuid
from collections import defaultdict
from typing import Any

import fitz
import pdfplumber
import pytesseract
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from PIL import Image, ImageDraw, ImageOps
from pytesseract import Output

try:
    import cv2
except Exception:  # pragma: no cover - optional dependency in some local environments
    cv2 = None

try:
    import numpy as np
except Exception:  # pragma: no cover - optional dependency in some local environments
    np = None


pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


MAX_FILE_SIZE = 10 * 1024 * 1024
MAX_RASTER_PAGES = 3
MAX_PREVIEW_WIDTH = 1000
APP_VERSION = "1.0.0"
OCR_CONFIG = "--oem 3 --psm 6 preserve_interword_spaces=1"
COMMON_TESSERACT_PATHS = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
)

PII_PATTERNS = {
    "aadhaar": r"\b[2-9]{1}[0-9]{3}\s[0-9]{4}\s[0-9]{4}\b",
    "pan": r"\b[A-Z]{5}[0-9]{4}[A-Z]{1}\b",
    "phone": r"\b(?:\+91[\-\s]?)?[6-9]\d{9}\b",
    "email": r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b",
}

SEVERITY_MAP = {
    "aadhaar": "high",
    "pan": "high",
    "phone": "medium",
    "email": "medium",
}

MAGIC_BYTES = {
    "pdf": b"%PDF",
    "png": b"\x89PNG\r\n\x1a\n",
    "jpeg": b"\xff\xd8\xff",
}

PAN_LETTER_FROM_DIGIT = {
    "0": "O",
    "1": "I",
    "2": "Z",
    "5": "S",
    "6": "G",
    "8": "B",
}
PAN_DIGIT_FROM_LETTER = {
    "O": "0",
    "Q": "0",
    "D": "0",
    "I": "1",
    "L": "1",
    "Z": "2",
    "S": "5",
    "B": "8",
    "G": "6",
}
EMAIL_ALPHA_FROM_DIGIT = {
    "0": "o",
    "1": "l",
    "5": "s",
    "8": "b",
}
EMAIL_RELAXED_PATTERN = re.compile(
    r"[a-z0-9][a-z0-9._%+\-]{0,63}\s*@\s*[a-z0-9.\-]+\s*\.\s*[a-z]{2,10}",
    re.IGNORECASE,
)

scan_cache: dict[tuple[str, str], dict[str, Any]] = {}
logger = logging.getLogger("pii_shield")


app = FastAPI(title="PII Shield", version=APP_VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def configure_tesseract() -> None:
    override = os.getenv("TESSERACT_CMD")
    candidates = [override] if override else []
    candidates.extend(COMMON_TESSERACT_PATHS)

    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            pytesseract.pytesseract.tesseract_cmd = candidate
            return


def ocr_is_available() -> bool:
    configure_tesseract()
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def error_response(status_code: int, error: str, detail: str | None = None) -> JSONResponse:
    payload: dict[str, Any] = {"error": error}
    if detail:
        payload["detail"] = detail
    return JSONResponse(status_code=status_code, content=payload)


def detect_file_type(file_bytes: bytes) -> str | None:
    if file_bytes.startswith(MAGIC_BYTES["pdf"]):
        return "pdf"
    if file_bytes.startswith(MAGIC_BYTES["png"]):
        return "png"
    if file_bytes.startswith(MAGIC_BYTES["jpeg"]):
        return "jpeg"
    return None


def file_hash(file_bytes: bytes) -> str:
    return hashlib.sha256(file_bytes).hexdigest()


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def safe_float(value: Any, default: float = -1.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def preprocess_image(image: Image.Image) -> Image.Image:
    base_image = ImageOps.exif_transpose(image).convert("RGB")
    if cv2 is None or np is None:
        return ImageOps.autocontrast(base_image)

    gray = cv2.cvtColor(np.array(base_image), cv2.COLOR_RGB2GRAY)
    denoised = cv2.fastNlMeansDenoising(gray, None, h=17, templateWindowSize=7, searchWindowSize=21)
    contrast = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(denoised)

    height, width = contrast.shape[:2]
    longest_side = max(width, height)
    if longest_side < 1500:
        scale = min(2.0, 1500.0 / longest_side)
        contrast = cv2.resize(
            contrast,
            None,
            fx=scale,
            fy=scale,
            interpolation=cv2.INTER_CUBIC,
        )

    thresholded = cv2.adaptiveThreshold(
        contrast,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        15,
    )
    thresholded = cv2.medianBlur(thresholded, 3)
    return Image.fromarray(thresholded)


def preprocess_image_soft(image: Image.Image) -> Image.Image:
    base_image = ImageOps.exif_transpose(image).convert("RGB")
    if cv2 is None or np is None:
        return ImageOps.autocontrast(base_image)

    gray = cv2.cvtColor(np.array(base_image), cv2.COLOR_RGB2GRAY)
    contrast = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)

    height, width = contrast.shape[:2]
    longest_side = max(width, height)
    if longest_side < 1400:
        scale = min(2.0, 1400.0 / longest_side)
        contrast = cv2.resize(
            contrast,
            None,
            fx=scale,
            fy=scale,
            interpolation=cv2.INTER_CUBIC,
        )

    return Image.fromarray(contrast)


def clamp_ratio(value: float) -> float:
    return max(0.0, min(1.0, round(value, 6)))


def normalize_bbox(
    x: float,
    y: float,
    w: float,
    h: float,
    width: float,
    height: float,
) -> dict[str, float] | None:
    if width <= 0 or height <= 0:
        return None
    if w <= 0 or h <= 0:
        return None

    return {
        "x": clamp_ratio(x / width),
        "y": clamp_ratio(y / height),
        "w": clamp_ratio(w / width),
        "h": clamp_ratio(h / height),
    }


def normalize_text(text: str) -> str:
    if not text:
        return ""

    normalized = unicodedata.normalize("NFKC", text).replace("\r", "\n")
    cleaned_chars: list[str] = []

    for index, char in enumerate(normalized):
        if char in {"\n", "\t"}:
            cleaned_chars.append(" ")
            continue
        if ord(char) < 32:
            continue

        prev_char = normalized[index - 1] if index > 0 else " "
        next_char = normalized[index + 1] if index + 1 < len(normalized) else " "
        near_digit = prev_char.isdigit() or next_char.isdigit()

        if char in {"O", "o"} and near_digit:
            cleaned_chars.append("0")
        elif char in {"I", "l", "|"} and near_digit:
            cleaned_chars.append("1")
        elif char in {"S", "s"} and near_digit:
            cleaned_chars.append("5")
        else:
            cleaned_chars.append(char)

    collapsed = "".join(cleaned_chars)
    collapsed = re.sub(r"[^A-Za-z0-9@._+\-:/\s]", " ", collapsed)
    collapsed = re.sub(r"\s+", " ", collapsed)
    return collapsed.strip()


def normalize_compact(text: str) -> str:
    return re.sub(r"[\s\-:/]+", "", normalize_text(text))


def normalize_email_text(text: str) -> str:
    cleaned = normalize_text(text).lower()
    repaired_chars: list[str] = []

    for index, char in enumerate(cleaned):
        prev_char = cleaned[index - 1] if index > 0 else " "
        next_char = cleaned[index + 1] if index + 1 < len(cleaned) else " "
        near_alpha = prev_char.isalpha() or next_char.isalpha() or prev_char in "@." or next_char in "@."
        if near_alpha and char in EMAIL_ALPHA_FROM_DIGIT:
            repaired_chars.append(EMAIL_ALPHA_FROM_DIGIT[char])
        else:
            repaired_chars.append(char)

    repaired = "".join(repaired_chars)
    repaired = re.sub(r"\s*@\s*", "@", repaired)
    repaired = re.sub(r"\s*\.\s*", ".", repaired)
    repaired = re.sub(r"[^a-z0-9@._%+\-]", "", repaired)
    repaired = re.sub(r"\.{2,}", ".", repaired)
    return repaired.strip(".")


def mask_value(pii_type: str, value: str) -> str:
    if pii_type == "aadhaar":
        digits = re.sub(r"\D", "", value)
        return f"XXXX-XXXX-{digits[-4:]}" if len(digits) >= 4 else "XXXX-XXXX-XXXX"
    if pii_type == "pan":
        compact = re.sub(r"[^A-Z0-9]", "", value.upper())
        return f"XXXXX{compact[5:9]}X" if len(compact) >= 10 else "XXXXXXXXXX"
    if pii_type == "phone":
        digits = re.sub(r"\D", "", value)
        return f"XXXXXX{digits[-4:]}" if len(digits) >= 4 else "XXXXXXXXXX"
    if pii_type == "email":
        local, _, domain = value.partition("@")
        if local and domain:
            return f"{local[0]}***@{domain}"
        return "***"
    return "XXXX"


def canonical_value(pii_type: str, value: str) -> str:
    if pii_type == "aadhaar":
        return re.sub(r"\D", "", value)
    if pii_type == "pan":
        return re.sub(r"[^A-Z0-9]", "", value.upper())
    if pii_type == "phone":
        digits = re.sub(r"\D", "", value)
        return digits[-10:] if len(digits) >= 10 else digits
    if pii_type == "email":
        return normalize_email_text(value)
    return normalize_compact(value)


def build_risk_score(findings: list[dict[str, Any]]) -> dict[str, Any]:
    high_count = sum(1 for finding in findings if finding["severity"] == "high")
    medium_count = sum(1 for finding in findings if finding["severity"] == "medium")
    if high_count > 0:
        level = "HIGH"
    elif medium_count > 0:
        level = "MEDIUM"
    else:
        level = "SAFE"
    return {
        "level": level,
        "total_findings": len(findings),
        "high_count": high_count,
        "medium_count": medium_count,
    }


def add_spacing_between_chars(chars: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any] | None]]:
    if not chars:
        return "", []

    ordered = sorted(chars, key=lambda char: (round(char.get("top", 0.0), 2), char.get("x0", 0.0)))
    parts: list[str] = []
    index_map: list[dict[str, Any] | None] = []
    previous: dict[str, Any] | None = None

    for char in ordered:
        if previous is not None:
            prev_bottom = previous.get("bottom", previous.get("top", 0.0))
            line_break = abs(char.get("top", 0.0) - previous.get("top", 0.0)) > max(
                3.0,
                (prev_bottom - previous.get("top", 0.0)) * 0.8,
            )
            gap = char.get("x0", 0.0) - previous.get("x1", 0.0)
            avg_size = max(previous.get("size", 8.0), 8.0)

            if line_break:
                parts.append("\n")
                index_map.append(None)
            elif gap > avg_size * 0.3:
                parts.append(" ")
                index_map.append(None)

        parts.append(char.get("text", ""))
        index_map.append(char)
        previous = char

    return "".join(parts), index_map


def group_chars_into_lines(chars: list[dict[str, Any]], tolerance: float = 3.0) -> list[list[dict[str, Any]]]:
    if not chars:
        return []

    ordered = sorted(chars, key=lambda char: (round(char.get("top", 0.0), 2), char.get("x0", 0.0)))
    lines: list[list[dict[str, Any]]] = [[ordered[0]]]

    for char in ordered[1:]:
        current_line = lines[-1]
        if abs(char.get("top", 0.0) - current_line[0].get("top", 0.0)) <= tolerance:
            current_line.append(char)
        else:
            lines.append([char])

    return lines


def map_pdf_bbox(
    finding_value: str,
    match_start: int,
    match_end: int,
    index_map: list[dict[str, Any] | None],
    chars: list[dict[str, Any]],
    page_width: float,
    page_height: float,
) -> dict[str, float] | None:
    matched_chars = [
        index_map[index]
        for index in range(match_start, min(match_end, len(index_map)))
        if index_map[index] is not None
    ]
    if matched_chars:
        left = min(char["x0"] for char in matched_chars)
        top = min(char["top"] for char in matched_chars)
        right = max(char["x1"] for char in matched_chars)
        bottom = max(char["bottom"] for char in matched_chars)
        bbox = normalize_bbox(left, top, right - left, bottom - top, page_width, page_height)
        if bbox:
            return bbox

    target = normalize_compact(finding_value)
    for line in group_chars_into_lines(chars):
        line_text = "".join(char.get("text", "") for char in line)
        if target and target in normalize_compact(line_text):
            left = min(char["x0"] for char in line)
            top = min(char["top"] for char in line)
            right = max(char["x1"] for char in line)
            bottom = max(char["bottom"] for char in line)
            bbox = normalize_bbox(left, top, right - left, bottom - top, page_width, page_height)
            if bbox:
                return bbox

    return None


def extract_pdf_pages(file_bytes: bytes) -> list[dict[str, Any]]:
    pages: list[dict[str, Any]] = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            chars = page.chars or []
            page_text, index_map = add_spacing_between_chars(chars)
            pages.append(
                {
                    "page_number": page_number,
                    "text": page_text,
                    "chars": chars,
                    "index_map": index_map,
                    "width": float(page.width),
                    "height": float(page.height),
                }
            )
    return pages


def score_ocr_words(words: list[dict[str, Any]]) -> float:
    if not words:
        return -1.0
    positive_conf = [max(word.get("conf", -1.0), 0.0) for word in words]
    avg_conf = sum(positive_conf) / max(len(positive_conf), 1)
    alnum_chars = sum(sum(char.isalnum() for char in word["text"]) for word in words)
    return avg_conf + min(alnum_chars, 80)


def build_ocr_words(ocr_data: dict[str, list[Any]]) -> tuple[str, list[dict[str, Any]]]:
    words: list[dict[str, Any]] = []
    parts: list[str] = []
    cursor = 0
    line_order: dict[tuple[int, int, int], int] = {}

    for index, raw_word in enumerate(ocr_data.get("text", [])):
        word = raw_word.strip()
        if not word:
            continue

        start = cursor + (1 if parts else 0)
        if parts:
            cursor += 1
        parts.append(word)
        end = start + len(word)
        cursor = end

        line_key = (
            safe_int(ocr_data.get("block_num", [0])[index]),
            safe_int(ocr_data.get("par_num", [0])[index]),
            safe_int(ocr_data.get("line_num", [0])[index]),
        )
        if line_key not in line_order:
            line_order[line_key] = len(line_order)

        words.append(
            {
                "text": word,
                "left": float(ocr_data["left"][index]),
                "top": float(ocr_data["top"][index]),
                "width": float(ocr_data["width"][index]),
                "height": float(ocr_data["height"][index]),
                "start": start,
                "end": end,
                "conf": safe_float(ocr_data.get("conf", ["-1"])[index]),
                "block_num": line_key[0],
                "par_num": line_key[1],
                "line_num": line_key[2],
                "line_index": line_order[line_key],
            }
        )

    return " ".join(parts), words


def ocr_words_from_image(image: Image.Image) -> tuple[str, list[dict[str, Any]]]:
    ocr_data = pytesseract.image_to_data(image, output_type=Output.DICT, config=OCR_CONFIG)
    return build_ocr_words(ocr_data)


def ocr_image_page(image: Image.Image, page_number: int) -> dict[str, Any]:
    primary_processed = preprocess_image(image)
    text, words = ocr_words_from_image(primary_processed)

    if score_ocr_words(words) < 55:
        fallback_processed = preprocess_image_soft(image)
        fallback_text, fallback_words = ocr_words_from_image(fallback_processed)
        if score_ocr_words(fallback_words) > score_ocr_words(words):
            primary_processed = fallback_processed
            text = fallback_text
            words = fallback_words

    return {
        "page_number": page_number,
        "text": text,
        "ocr_words": words,
        "width": float(primary_processed.width),
        "height": float(primary_processed.height),
    }


def extract_image_pages(file_bytes: bytes, file_type: str) -> list[dict[str, Any]]:
    if not ocr_is_available():
        raise ValueError("OCR engine unavailable")

    if file_type == "pdf":
        document = fitz.open(stream=file_bytes, filetype="pdf")
        try:
            pages: list[dict[str, Any]] = []
            for index, page in enumerate(document, start=1):
                pixmap = page.get_pixmap(alpha=False)
                image = Image.open(io.BytesIO(pixmap.tobytes("png"))).convert("RGB")
                pages.append(ocr_image_page(image, index))
            return pages
        finally:
            document.close()

    image = Image.open(io.BytesIO(file_bytes)).convert("RGB")
    return [ocr_image_page(image, 1)]


def union_word_boxes(
    words: list[dict[str, Any]],
    page_width: float,
    page_height: float,
) -> dict[str, float] | None:
    if not words:
        return None

    left = min(word["left"] for word in words)
    top = min(word["top"] for word in words)
    right = max(word["left"] + word["width"] for word in words)
    bottom = max(word["top"] + word["height"] for word in words)
    return normalize_bbox(left, top, right - left, bottom - top, page_width, page_height)


def map_ocr_bbox(
    finding_value: str,
    match_start: int,
    match_end: int,
    ocr_words: list[dict[str, Any]],
    page_width: float,
    page_height: float,
) -> dict[str, float] | None:
    covered_words = [
        word for word in ocr_words if word["start"] < match_end and word["end"] > match_start
    ]
    if not covered_words:
        target = normalize_compact(finding_value)
        for word in ocr_words:
            if target and target in normalize_compact(word["text"]):
                covered_words = [word]
                break

    return union_word_boxes(covered_words, page_width, page_height)


def iter_ocr_windows(ocr_words: list[dict[str, Any]], max_window_words: int = 6) -> list[list[dict[str, Any]]]:
    windows: list[list[dict[str, Any]]] = []
    total_words = len(ocr_words)

    for start in range(total_words):
        current_window: list[dict[str, Any]] = []
        base_word = ocr_words[start]

        for end in range(start, min(total_words, start + max_window_words)):
            word = ocr_words[end]
            if word["line_index"] - base_word["line_index"] > 1:
                break

            vertical_span = (word["top"] + word["height"]) - base_word["top"]
            if vertical_span > max(base_word["height"], word["height"]) * 4.0:
                break

            current_window.append(word)
            windows.append(list(current_window))

    return windows


def repair_pan_fragment(fragment: str) -> tuple[str | None, int]:
    compact = re.sub(r"[^A-Z0-9]", "", fragment.upper())
    if len(compact) != 10:
        return None, 0

    repaired: list[str] = []
    replacements = 0

    for index, char in enumerate(compact):
        needs_letter = index < 5 or index == 9
        if needs_letter:
            if char.isalpha():
                repaired.append(char)
            elif char in PAN_LETTER_FROM_DIGIT:
                repaired.append(PAN_LETTER_FROM_DIGIT[char])
                replacements += 1
            else:
                return None, 0
        else:
            if char.isdigit():
                repaired.append(char)
            elif char in PAN_DIGIT_FROM_LETTER:
                repaired.append(PAN_DIGIT_FROM_LETTER[char])
                replacements += 1
            else:
                return None, 0

    if replacements > 2:
        return None, 0
    return "".join(repaired), replacements


def detect_pan_from_words(words: list[dict[str, Any]]) -> dict[str, Any] | None:
    window_text = " ".join(word["text"] for word in words)
    compact = re.sub(r"[^A-Za-z0-9]", "", normalize_text(window_text).upper())
    if len(compact) < 10:
        return None

    best_value: str | None = None
    best_score = 0.0
    for index in range(0, len(compact) - 9):
        fragment = compact[index : index + 10]
        repaired, replacements = repair_pan_fragment(fragment)
        if not repaired:
            continue

        score = max(0.72, 0.93 - (replacements * 0.08))
        if score > best_score:
            best_value = repaired
            best_score = score

    if not best_value:
        return None

    return {
        "type": "pan",
        "raw_value": best_value,
        "confidence": round(best_score, 2),
        "matched_words": words,
    }


def best_phone_digits(text: str) -> tuple[str | None, float]:
    digits = re.sub(r"\D", "", normalize_text(text))
    if len(digits) < 10:
        return None, 0.0

    candidates: list[tuple[str, float]] = []

    if len(digits) == 10 and digits[0] in "6789":
        candidates.append((digits, 0.9))

    if len(digits) == 11 and digits.startswith("0") and digits[1] in "6789":
        candidates.append((digits[1:11], 0.87))

    if len(digits) == 12 and digits.startswith("91") and digits[2] in "6789":
        candidates.append((digits[2:12], 0.88))

    if not candidates:
        return None, 0.0

    return max(candidates, key=lambda item: item[1])


def detect_phone_from_words(words: list[dict[str, Any]]) -> dict[str, Any] | None:
    window_text = " ".join(word["text"] for word in words)
    if "@" in window_text:
        return None

    digits, score = best_phone_digits(window_text)
    if not digits:
        return None

    return {
        "type": "phone",
        "raw_value": digits,
        "confidence": round(score, 2),
        "matched_words": words,
    }


def best_aadhaar_digits(text: str) -> tuple[str | None, float]:
    digits = re.sub(r"\D", "", normalize_text(text))
    if len(digits) < 12:
        return None, 0.0

    candidates: list[tuple[str, float]] = []
    grouped_hint = bool(re.search(r"[2-9][0-9OIlS]{3}\s+[0-9OIlS]{4}\s+[0-9OIlS]{4}", text))

    for index in range(0, len(digits) - 11):
        fragment = digits[index : index + 12]
        if fragment[0] not in "23456789":
            continue
        if fragment.startswith("91") and len(fragment) == 12 and fragment[2] in "6789":
            continue

        score = 0.86 - (0.015 * min(index, 4))
        if grouped_hint:
            score += 0.04
        candidates.append((fragment, min(score, 0.92)))

    if not candidates:
        return None, 0.0

    return max(candidates, key=lambda item: item[1])


def detect_aadhaar_from_words(words: list[dict[str, Any]]) -> dict[str, Any] | None:
    window_text = " ".join(word["text"] for word in words)
    digits, score = best_aadhaar_digits(window_text)
    if not digits:
        return None

    formatted = f"{digits[0:4]} {digits[4:8]} {digits[8:12]}"
    return {
        "type": "aadhaar",
        "raw_value": formatted,
        "confidence": round(score, 2),
        "matched_words": words,
    }


def detect_email_from_words(words: list[dict[str, Any]]) -> dict[str, Any] | None:
    window_text = " ".join(word["text"] for word in words)
    normalized_email = normalize_email_text(window_text)
    if "@" not in normalized_email:
        return None

    match = EMAIL_RELAXED_PATTERN.search(normalized_email)
    if not match:
        return None

    candidate = match.group(0)
    if candidate.count("@") != 1:
        return None

    local, domain = candidate.split("@", 1)
    if not local or "." not in domain:
        return None

    tld = domain.rsplit(".", 1)[-1]
    if not (2 <= len(tld) <= 10):
        return None

    repair_cost = abs(len(re.sub(r"\s+", "", window_text)) - len(candidate))
    score = max(0.72, 0.9 - (repair_cost * 0.03))
    return {
        "type": "email",
        "raw_value": candidate,
        "confidence": round(score, 2),
        "matched_words": words,
    }


FUZZY_DETECTORS = (
    detect_pan_from_words,
    detect_phone_from_words,
    detect_email_from_words,
    detect_aadhaar_from_words,
)


def build_finding(
    pii_type: str,
    raw_value: str,
    page_number: int,
    confidence: float,
    bbox: dict[str, float] | None,
) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "type": pii_type,
        "value": mask_value(pii_type, raw_value),
        "raw_value": raw_value,
        "page": page_number,
        "severity": SEVERITY_MAP[pii_type],
        "confidence": round(confidence, 2),
        "bbox": bbox,
    }


def collect_exact_findings(
    page_payloads: list[dict[str, Any]],
    mode: str,
) -> tuple[list[dict[str, Any]], set[tuple[str, int, str]]]:
    findings: list[dict[str, Any]] = []
    seen: set[tuple[str, int, str]] = set()

    for page_payload in page_payloads:
        page_text = page_payload["text"]
        if not page_text:
            continue

        for pii_type, pattern in PII_PATTERNS.items():
            for match in re.finditer(pattern, page_text):
                canonical = canonical_value(pii_type, match.group())
                dedupe_key = (pii_type, page_payload["page_number"], canonical)
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)

                if mode == "pdf_text":
                    bbox = map_pdf_bbox(
                        match.group(),
                        match.start(),
                        match.end(),
                        page_payload["index_map"],
                        page_payload["chars"],
                        page_payload["width"],
                        page_payload["height"],
                    )
                    confidence = 0.98
                else:
                    bbox = map_ocr_bbox(
                        match.group(),
                        match.start(),
                        match.end(),
                        page_payload["ocr_words"],
                        page_payload["width"],
                        page_payload["height"],
                    )
                    confidence = 0.88

                findings.append(
                    build_finding(
                        pii_type=pii_type,
                        raw_value=match.group(),
                        page_number=page_payload["page_number"],
                        confidence=confidence,
                        bbox=bbox,
                    )
                )

    return findings, seen


def collect_fuzzy_ocr_findings(
    page_payloads: list[dict[str, Any]],
    seen: set[tuple[str, int, str]],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []

    for page_payload in page_payloads:
        windows = iter_ocr_windows(page_payload["ocr_words"])
        per_type_best: dict[tuple[str, str], dict[str, Any]] = {}

        for window in windows:
            for detector in FUZZY_DETECTORS:
                detected = detector(window)
                if not detected:
                    continue

                pii_type = detected["type"]
                canonical = canonical_value(pii_type, detected["raw_value"])
                dedupe_key = (pii_type, page_payload["page_number"], canonical)
                if dedupe_key in seen:
                    continue

                record_key = (pii_type, canonical)
                existing = per_type_best.get(record_key)
                if existing is None or detected["confidence"] > existing["confidence"]:
                    per_type_best[record_key] = detected

        for detected in per_type_best.values():
            pii_type = detected["type"]
            canonical = canonical_value(pii_type, detected["raw_value"])
            dedupe_key = (pii_type, page_payload["page_number"], canonical)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            bbox = union_word_boxes(
                detected["matched_words"],
                page_payload["width"],
                page_payload["height"],
            )
            findings.append(
                build_finding(
                    pii_type=pii_type,
                    raw_value=detected["raw_value"],
                    page_number=page_payload["page_number"],
                    confidence=detected["confidence"],
                    bbox=bbox,
                )
            )

    return findings


def collect_regex_findings(page_payloads: list[dict[str, Any]], mode: str) -> list[dict[str, Any]]:
    findings, seen = collect_exact_findings(page_payloads, mode)
    if mode == "ocr_image":
        findings.extend(collect_fuzzy_ocr_findings(page_payloads, seen))

    findings.sort(key=lambda item: (item["page"], item["type"], canonical_value(item["type"], item["raw_value"])))
    return findings


def build_pdf_previews(file_bytes: bytes) -> tuple[int, list[dict[str, Any]]]:
    document = fitz.open(stream=file_bytes, filetype="pdf")
    try:
        page_count = document.page_count
        previews: list[dict[str, Any]] = []

        for index in range(min(page_count, MAX_RASTER_PAGES)):
            page = document.load_page(index)
            previews.append(
                {
                    "page_number": index + 1,
                    **render_pdf_page_preview(page),
                }
            )

        return page_count, previews
    finally:
        document.close()


def render_pdf_page_preview(page: fitz.Page) -> dict[str, Any]:
    rect = page.rect
    scale = min(MAX_PREVIEW_WIDTH / rect.width, 2.0)
    scale = max(scale, 0.5)
    pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
    image_bytes = pixmap.tobytes("png")
    return {
        "image_b64": base64.b64encode(image_bytes).decode("ascii"),
        "width": pixmap.width,
        "height": pixmap.height,
    }


def build_image_previews(file_bytes: bytes) -> tuple[int, list[dict[str, Any]]]:
    image = Image.open(io.BytesIO(file_bytes)).convert("RGB")
    width, height = image.size
    if width > MAX_PREVIEW_WIDTH:
        ratio = MAX_PREVIEW_WIDTH / width
        image = image.resize((MAX_PREVIEW_WIDTH, max(1, int(height * ratio))), Image.Resampling.LANCZOS)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return 1, [
        {
            "page_number": 1,
            "image_b64": base64.b64encode(buffer.getvalue()).decode("ascii"),
            "width": image.width,
            "height": image.height,
        }
    ]


def cache_findings(file_digest: str, findings: list[dict[str, Any]]) -> None:
    keys_to_delete = [key for key in scan_cache if key[0] == file_digest]
    for key in keys_to_delete:
        scan_cache.pop(key, None)

    for finding in findings:
        scan_cache[(file_digest, finding["id"])] = {
            "page": finding["page"],
            "bbox": finding["bbox"],
        }


def render_redacted_pdf(file_bytes: bytes, file_type: str, finding_ids: list[str]) -> bytes:
    file_digest = file_hash(file_bytes)
    cached_keys = {key for key in scan_cache if key[0] == file_digest}
    if not cached_keys:
        raise LookupError("file_mismatch")

    entries = []
    for finding_id in finding_ids:
        cache_key = (file_digest, finding_id)
        if cache_key not in scan_cache:
            raise KeyError("invalid_finding_ids")
        entries.append(scan_cache[cache_key])

    redactions_by_page: dict[int, list[dict[str, Any] | None]] = defaultdict(list)
    for entry in entries:
        redactions_by_page[entry["page"]].append(entry["bbox"])

    output = fitz.open()

    if file_type == "pdf":
        document = fitz.open(stream=file_bytes, filetype="pdf")
        try:
            for index in range(document.page_count):
                page = document.load_page(index)
                pixmap = page.get_pixmap(alpha=False)
                image = Image.open(io.BytesIO(pixmap.tobytes("png"))).convert("RGB")
                draw_redactions(image, redactions_by_page.get(index + 1, []))
                append_image_page(output, image)
        finally:
            document.close()
    else:
        image = Image.open(io.BytesIO(file_bytes)).convert("RGB")
        draw_redactions(image, redactions_by_page.get(1, []))
        append_image_page(output, image)

    pdf_bytes = output.tobytes(deflate=True)
    output.close()
    return pdf_bytes


def draw_redactions(image: Image.Image, redactions: list[dict[str, Any] | None]) -> None:
    draw = ImageDraw.Draw(image)
    for bbox in redactions:
        if not bbox:
            continue
        left = int(bbox["x"] * image.width)
        top = int(bbox["y"] * image.height)
        right = int((bbox["x"] + bbox["w"]) * image.width)
        bottom = int((bbox["y"] + bbox["h"]) * image.height)
        draw.rectangle([left, top, right, bottom], fill="black")


def append_image_page(document: fitz.Document, image: Image.Image) -> None:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    page = document.new_page(width=image.width, height=image.height)
    page.insert_image(page.rect, stream=buffer.getvalue())


async def read_upload_file(file: UploadFile) -> tuple[bytes, str]:
    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        raise ValueError("file_too_large")

    detected = detect_file_type(file_bytes)
    if detected is None:
        raise TypeError("unsupported_file_type")

    return file_bytes, detected


@app.on_event("startup")
async def log_startup_status() -> None:
    if ocr_is_available():
        logger.info("OCR is available for image uploads and image-only PDFs.")
    else:
        logger.warning(
            "OCR is unavailable. Install Tesseract OCR or set TESSERACT_CMD to enable PNG/JPG and image-only PDF scanning."
        )


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "ocr_available": ocr_is_available(),
        "version": APP_VERSION,
    }


@app.post("/scan")
async def scan(file: UploadFile = File(...)) -> Response:
    try:
        file_bytes, detected_type = await read_upload_file(file)
    except ValueError as exc:
        logger.warning("Scan rejected for %s: %s", file.filename or "upload", exc)
        return error_response(400, str(exc))
    except TypeError as exc:
        logger.warning("Scan rejected for %s: %s", file.filename or "upload", exc)
        return error_response(400, str(exc))
    except Exception as exc:
        logger.exception("Scan failed before processing for %s", file.filename or "upload")
        return error_response(500, "processing_failed", str(exc))

    try:
        if detected_type == "pdf":
            page_payloads = extract_pdf_pages(file_bytes)
            joined_text = "".join(page["text"] for page in page_payloads).strip()
            if joined_text:
                mode = "pdf_text"
            else:
                page_payloads = extract_image_pages(file_bytes, detected_type)
                mode = "ocr_image"
            page_count, pages = build_pdf_previews(file_bytes)
        else:
            page_payloads = extract_image_pages(file_bytes, detected_type)
            mode = "ocr_image"
            page_count, pages = build_image_previews(file_bytes)

        findings = collect_regex_findings(page_payloads, mode)
        if mode == "ocr_image" and not "".join(page["text"] for page in page_payloads).strip():
            return error_response(400, "no_text_extracted")

        cache_findings(file_hash(file_bytes), findings)
        payload = {
            "mode": mode,
            "page_count": page_count,
            "pages": pages,
            "findings": findings,
            "risk_score": build_risk_score(findings),
        }
        return JSONResponse(content=payload)
    except ValueError:
        logger.warning(
            "Scan returned no_text_extracted for %s (%s). OCR available: %s",
            file.filename or "upload",
            detected_type,
            ocr_is_available(),
        )
        return error_response(400, "no_text_extracted")
    except Exception as exc:
        logger.exception("Scan processing failed for %s", file.filename or "upload")
        return error_response(500, "processing_failed", str(exc))


@app.post("/redact")
async def redact(file: UploadFile = File(...), finding_ids: str = Form(...)) -> Response:
    try:
        file_bytes, detected_type = await read_upload_file(file)
    except ValueError as exc:
        logger.warning("Redaction rejected for %s: %s", file.filename or "upload", exc)
        if str(exc) == "file_too_large":
            return error_response(400, "file_mismatch")
        return error_response(400, "invalid_finding_ids")
    except TypeError:
        logger.warning("Redaction rejected for %s: unsupported file type", file.filename or "upload")
        return error_response(400, "file_mismatch")
    except Exception as exc:
        logger.exception("Redaction failed before processing for %s", file.filename or "upload")
        return error_response(500, "redaction_failed", str(exc))

    try:
        parsed_ids = json.loads(finding_ids)
        if not isinstance(parsed_ids, list) or not all(isinstance(item, str) for item in parsed_ids):
            raise ValueError("invalid_finding_ids")
    except Exception:
        return error_response(400, "invalid_finding_ids")

    try:
        pdf_bytes = render_redacted_pdf(file_bytes, detected_type, parsed_ids)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=pii-shield-redacted.pdf"},
        )
    except LookupError:
        logger.warning("Redaction file mismatch for %s", file.filename or "upload")
        return error_response(400, "file_mismatch")
    except KeyError:
        logger.warning("Redaction received invalid finding ids for %s", file.filename or "upload")
        return error_response(400, "invalid_finding_ids")
    except Exception as exc:
        logger.exception("Redaction processing failed for %s", file.filename or "upload")
        return error_response(500, "redaction_failed", str(exc))
