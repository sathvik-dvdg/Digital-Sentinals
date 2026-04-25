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
except Exception:  # pragma: no cover
    cv2 = None

try:
    import numpy as np
except Exception:  # pragma: no cover
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

# ==========================================================================
# PII PATTERNS — strict primary regexes (high-confidence matches)
# ==========================================================================
PII_PATTERNS = {
    # Aadhaar: 3 groups of 4 digits separated by space/hyphen, first digit 2-9
    "aadhaar": r"\b[2-9]\d{3}[\s\-]\d{4}[\s\-]\d{4}\b",
    # PAN: 3 letters + holder-type + letter + 4 digits + check letter
    "pan": r"\b[A-Z]{3}[PCHFATBLJG][A-Z]\d{4}[A-Z]\b",
    # Phone: Indian mobile, 10 digits starting 6-9, optional +91 prefix
    "phone": r"(?<!\d)(?:\+91[\s\-]?)?[6-9]\d{9}(?!\d)",
    # Email: standard email pattern
    "email": r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b",
}

# Supplementary: continuous 12-digit Aadhaar (no separators — lower confidence)
AADHAAR_CONTINUOUS_RE = re.compile(r"(?<!\d)[2-9]\d{11}(?!\d)")

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

# ---------- PAN repair tables ----------
PAN_LETTER_FROM_DIGIT = {"0": "O", "1": "I", "2": "Z", "5": "S", "6": "G", "8": "B"}
PAN_DIGIT_FROM_LETTER = {"O": "0", "Q": "0", "D": "0", "I": "1", "L": "1", "Z": "2", "S": "5", "B": "8", "G": "6"}
PAN_VALID_FOURTH_CHARS = set("PCHFATBLJG")
PAN_POSITIVE_CONTEXT = {"PAN", "PERMANENT", "ACCOUNT", "NUMBER", "INCOME", "TAX", "GOVT", "INDIA", "DEPARTMENT", "TAXPAYER"}
PAN_NEGATIVE_CONTEXT = {"SIGNATURE", "SIGN", "STAMP", "QR", "CODE", "SCAN", "DECORATIVE", "LOGO", "PHOTO", "SIGN HERE"}

# ---------- Email tables ----------
EMAIL_ALPHA_FROM_DIGIT = {"0": "o", "1": "l", "5": "s", "8": "b"}
EMAIL_RELAXED_RE = re.compile(
    r"[a-z0-9][a-z0-9._%+\-]{0,63}\s*@\s*[a-z0-9.\-]+\s*\.\s*[a-z]{2,10}",
    re.IGNORECASE,
)
VALID_TLDS = {
    "com", "org", "net", "edu", "gov", "mil", "int",
    "co", "io", "in", "uk", "us", "ca", "au", "de", "fr", "jp",
    "info", "biz", "name", "pro", "aero", "coop", "museum",
    "ac", "ai", "app", "dev", "xyz", "me", "tv", "cc",
}
KNOWN_EMAIL_DOMAINS = {
    "gmail.com", "yahoo.com", "outlook.com", "hotmail.com",
    "rediffmail.com", "protonmail.com", "icloud.com",
    "aol.com", "mail.com", "zoho.com", "yandex.com",
    "live.com", "msn.com", "proton.me",
}

# ---------- Aadhaar context ----------
AADHAAR_POSITIVE_CONTEXT = {
    "AADHAAR", "AADHAR", "UIDAI", "UID", "UNIQUE", "IDENTIFICATION",
    "ENROLMENT", "ENROLLMENT", "VID", "GOVT", "GOVERNMENT",
}

# ---------- Phone context ----------
PHONE_POSITIVE_CONTEXT = {
    "PHONE", "MOBILE", "MOB", "CELL", "TEL", "CONTACT", "CALL",
    "WHATSAPP", "PH", "FAX", "LANDLINE", "TELEPHONE",
}

# ==========================================================================
# Verhoeff checksum (Aadhaar validation)
# ==========================================================================
VERHOEFF_D = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
    [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
    [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
    [4, 0, 1, 2, 3, 9, 5, 6, 7, 8],
    [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
    [6, 5, 9, 8, 7, 1, 0, 4, 3, 2],
    [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
    [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
    [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
]
VERHOEFF_P = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
    [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
    [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
    [9, 4, 5, 3, 1, 2, 6, 8, 7, 0],
    [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5],
    [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
]


def verhoeff_checksum(number: str) -> bool:
    """Validate 12-digit Aadhaar using Verhoeff algorithm."""
    digits = re.sub(r"\D", "", number)
    if len(digits) != 12:
        return False
    c = 0
    for i, digit in enumerate(reversed(digits)):
        c = VERHOEFF_D[c][VERHOEFF_P[i % 8][int(digit)]]
    return c == 0


# ==========================================================================
# VALIDATION LAYER — isolated, testable validators per PII type
# ==========================================================================

def validate_aadhaar(digits: str) -> tuple[float, str]:
    """Validate 12-digit Aadhaar candidate.
    Returns (confidence, reason). confidence=0.0 means reject.
    """
    if len(digits) != 12:
        return 0.0, "wrong length"
    if digits[0] not in "23456789":
        return 0.0, "invalid first digit"
    if len(set(digits)) <= 2:
        return 0.0, "too few unique digits"

    # Reject fully sequential
    if all(int(digits[i + 1]) == (int(digits[i]) + 1) % 10 for i in range(11)):
        return 0.0, "sequential pattern"

    # Reject phone-like: 91 + mobile
    if digits[:2] == "91" and digits[2] in "6789":
        return 0.0, "looks like +91 phone"

    # Reject repeating groups like 111111111111
    groups = [digits[i:i + 4] for i in range(0, 12, 4)]
    if len(set(groups)) == 1:
        return 0.0, "repeating group pattern"

    if verhoeff_checksum(digits):
        return 0.95, "Verhoeff checksum passed"

    # Checksum fails — might be OCR error on one digit
    return 0.55, "Verhoeff checksum failed (possible OCR error)"


def validate_pan(value: str, page_context: str = "") -> tuple[float, str]:
    """Validate a 10-char PAN candidate. Returns (confidence, reason)."""
    compact = re.sub(r"[^A-Z0-9]", "", value.upper())
    if len(compact) != 10:
        return 0.0, "wrong length"

    # Structural: AAAA A 9999 A
    for i in range(5):
        if not compact[i].isalpha():
            return 0.0, f"position {i} must be letter"
    if compact[3] not in PAN_VALID_FOURTH_CHARS:
        return 0.0, "invalid holder type (position 4)"
    for i in range(5, 9):
        if not compact[i].isdigit():
            return 0.0, f"position {i} must be digit"
    if not compact[9].isalpha():
        return 0.0, "position 10 must be letter"
    if compact[5:9] == "0000":
        return 0.0, "zero serial"

    # Reject low-entropy
    if len(set(compact)) <= 3:
        return 0.0, "too few unique chars"

    score = 0.90
    reason = "Structural match"
    upper_ctx = page_context.upper()

    if any(kw in upper_ctx for kw in PAN_POSITIVE_CONTEXT):
        score = 0.97
        reason = "Structural match + context keywords"
    elif any(kw in upper_ctx for kw in PAN_NEGATIVE_CONTEXT):
        score = 0.55
        reason = "Structural match but negative context"

    return score, reason


def validate_phone(digits: str, page_text: str = "") -> tuple[float, str]:
    """Validate 10-digit Indian phone candidate. Returns (confidence, reason)."""
    if len(digits) != 10:
        return 0.0, "wrong length"
    if digits[0] not in "6789":
        return 0.0, "invalid first digit"
    if len(set(digits)) <= 2:
        return 0.0, "too few unique digits"

    # Sequential reject
    if all(int(digits[i + 1]) == (int(digits[i]) + 1) % 10 for i in range(9)):
        return 0.0, "sequential"

    # Check if embedded in longer digit run
    if page_text:
        # Find all occurrences and check neighbors
        idx = 0
        while True:
            idx = page_text.find(digits, idx)
            if idx < 0:
                break
            before = page_text[max(0, idx - 3):idx]
            after = page_text[idx + 10:idx + 13]
            adjacent_before = sum(1 for c in before if c.isdigit())
            adjacent_after = sum(1 for c in after if c.isdigit())
            if adjacent_before >= 2 or adjacent_after >= 2:
                return 0.0, "embedded in longer number"
            idx += 1

    score = 0.80
    reason = "Pattern match"
    if page_text and any(kw in page_text.upper() for kw in PHONE_POSITIVE_CONTEXT):
        score = 0.93
        reason = "Pattern match + context keywords"

    return score, reason


def validate_email(email: str) -> tuple[float, str]:
    """Validate email candidate. Returns (confidence, reason)."""
    if email.count("@") != 1:
        return 0.0, "multiple @ signs"

    local, domain = email.split("@", 1)
    if not local or not domain or "." not in domain:
        return 0.0, "missing local/domain/dot"
    if len(local) < 2 or len(local) > 64:
        return 0.0, "local part length"

    parts = domain.split(".")
    tld = parts[-1].lower()
    if len(tld) < 2 or len(tld) > 10:
        return 0.0, "bad TLD length"
    if any(len(p) == 0 for p in parts):
        return 0.0, "empty domain segment"
    if parts[0].isdigit():
        return 0.0, "numeric domain base"
    if ".." in email or email.startswith(".") or email.endswith("."):
        return 0.0, "malformed dots"

    # Reject if local part is all digits (likely OCR noise from numbers)
    if re.fullmatch(r"\d+", local):
        return 0.0, "all-digit local part"

    if domain.lower() in KNOWN_EMAIL_DOMAINS:
        return 0.96, "Known email domain"
    if tld in VALID_TLDS:
        return 0.88, "Recognized TLD"
    return 0.78, "Unknown TLD"


# ==========================================================================
# PAN REPAIR (for OCR-corrupted PAN strings)
# ==========================================================================

def is_impossible_pan(pan: str) -> bool:
    if len(set(pan)) <= 3:
        return True
    for i in range(len(pan) - 4):
        if (ord(pan[i + 1]) == ord(pan[i]) + 1
                and ord(pan[i + 2]) == ord(pan[i]) + 2
                and ord(pan[i + 3]) == ord(pan[i]) + 3):
            return True
    return False


def repair_pan_fragment(fragment: str) -> tuple[str | None, int]:
    compact = re.sub(r"[^A-Z0-9]", "", fragment.upper())
    if len(compact) != 10:
        return None, 0
    if is_impossible_pan(compact):
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
            if index == 3 and repaired[-1] not in PAN_VALID_FOURTH_CHARS:
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

    result = "".join(repaired)
    if result[5:9] == "0000":
        return None, 0

    return result, replacements


# ==========================================================================
# TEXT NORMALIZATION
# ==========================================================================

def normalize_text(text: str) -> str:
    if not text:
        return ""

    normalized = unicodedata.normalize("NFKC", text).replace("\r", "\n")
    cleaned: list[str] = []

    for i, char in enumerate(normalized):
        if char in {"\n", "\t"}:
            cleaned.append(" ")
            continue
        if ord(char) < 32:
            continue

        prev = normalized[i - 1] if i > 0 else " "
        nxt = normalized[i + 1] if i + 1 < len(normalized) else " "
        near_digit = prev.isdigit() or nxt.isdigit()

        if char in {"O", "o"} and near_digit:
            cleaned.append("0")
        elif char in {"I", "l", "|"} and near_digit:
            cleaned.append("1")
        elif char in {"S", "s"} and near_digit:
            cleaned.append("5")
        else:
            cleaned.append(char)

    collapsed = "".join(cleaned)
    collapsed = re.sub(r"[^A-Za-z0-9@._+\-:/\s]", " ", collapsed)
    collapsed = re.sub(r"\s+", " ", collapsed)
    return collapsed.strip()


def normalize_compact(text: str) -> str:
    return re.sub(r"[\s\-:/]+", "", normalize_text(text))


def normalize_email_text(text: str) -> str:
    cleaned = normalize_text(text).lower()
    repaired: list[str] = []

    for i, char in enumerate(cleaned):
        prev = cleaned[i - 1] if i > 0 else " "
        nxt = cleaned[i + 1] if i + 1 < len(cleaned) else " "
        near_alpha = prev.isalpha() or nxt.isalpha() or prev in "@." or nxt in "@."
        if near_alpha and char in EMAIL_ALPHA_FROM_DIGIT:
            repaired.append(EMAIL_ALPHA_FROM_DIGIT[char])
        else:
            repaired.append(char)

    result = "".join(repaired)
    result = re.sub(r"\s*@\s*", "@", result)
    result = re.sub(r"\s*\.\s*", ".", result)
    result = re.sub(r"[^a-z0-9@._%+\-]", "", result)
    result = re.sub(r"\.{2,}", ".", result)
    return result.strip(".")


# ==========================================================================
# MASKING AND CANONICAL
# ==========================================================================

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
    high = sum(1 for f in findings if f["severity"] == "high")
    med = sum(1 for f in findings if f["severity"] == "medium")
    level = "HIGH" if high > 0 else ("MEDIUM" if med > 0 else "SAFE")
    return {"level": level, "total_findings": len(findings), "high_count": high, "medium_count": med}


# ==========================================================================
# BBOX MAPPING — the core problem, now properly layered
# ==========================================================================

def clamp_ratio(value: float) -> float:
    return max(0.0, min(1.0, round(value, 6)))


def normalize_bbox(
    x: float, y: float, w: float, h: float,
    width: float, height: float,
) -> dict[str, float] | None:
    if width <= 0 or height <= 0 or w <= 0 or h <= 0:
        return None
    return {
        "x": clamp_ratio(x / width),
        "y": clamp_ratio(y / height),
        "w": clamp_ratio(w / width),
        "h": clamp_ratio(h / height),
    }


def union_word_boxes(
    words: list[dict[str, Any]],
    page_width: float,
    page_height: float,
) -> dict[str, float] | None:
    if not words:
        return None
    left = min(w["left"] for w in words)
    top = min(w["top"] for w in words)
    right = max(w["left"] + w["width"] for w in words)
    bottom = max(w["top"] + w["height"] for w in words)
    return normalize_bbox(left, top, right - left, bottom - top, page_width, page_height)


def map_ocr_bbox(
    finding_value: str,
    match_start: int,
    match_end: int,
    ocr_words: list[dict[str, Any]],
    page_width: float,
    page_height: float,
) -> dict[str, float] | None:
    """4-tier OCR bbox mapping (fixes the core mapping weakness).

    Tier 1: exact character-index overlap (original logic)
    Tier 2: normalized-text scan across ALL words
    Tier 3: sliding window of consecutive words matching digit/char sequence
    Tier 4: full-line bbox for the line containing any matching word
    """
    # --- Tier 1: direct index overlap ---
    covered = [w for w in ocr_words if w["start"] < match_end and w["end"] > match_start]
    if covered:
        bbox = union_word_boxes(covered, page_width, page_height)
        if bbox:
            return bbox

    # --- Tier 2: normalized compact scan ---
    target = normalize_compact(finding_value)
    if target:
        # Build a running compact string from words, tracking which words contributed
        running = ""
        word_indices: list[list[int]] = []  # for each char in running, which word index
        for wi, w in enumerate(ocr_words):
            w_compact = normalize_compact(w["text"])
            for c in w_compact:
                running += c
                word_indices.append([wi])

        idx = running.find(target)
        if idx >= 0:
            matched_word_set = set()
            for ci in range(idx, idx + len(target)):
                if ci < len(word_indices):
                    matched_word_set.update(word_indices[ci])
            matched_words = [ocr_words[i] for i in sorted(matched_word_set)]
            bbox = union_word_boxes(matched_words, page_width, page_height)
            if bbox:
                return bbox

    # --- Tier 3: sliding window of adjacent words ---
    if target:
        for start_idx in range(len(ocr_words)):
            accumulated = ""
            window_words = []
            for end_idx in range(start_idx, min(start_idx + 8, len(ocr_words))):
                w = ocr_words[end_idx]
                accumulated += normalize_compact(w["text"])
                window_words.append(w)
                if target in accumulated:
                    bbox = union_word_boxes(window_words, page_width, page_height)
                    if bbox:
                        return bbox
                if len(accumulated) > len(target) + 20:
                    break

    # --- Tier 4: line-level fallback ---
    if covered:
        # Use line_index of first covered word, grab entire line
        line_idx = covered[0].get("line_index")
        if line_idx is not None:
            line_words = [w for w in ocr_words if w.get("line_index") == line_idx]
            bbox = union_word_boxes(line_words, page_width, page_height)
            if bbox:
                return bbox

    # Single-word fallback
    if target:
        for w in ocr_words:
            if target in normalize_compact(w["text"]):
                return union_word_boxes([w], page_width, page_height)

    return None


# ---------- PDF (char-level) mapping ----------

def add_spacing_between_chars(chars: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any] | None]]:
    if not chars:
        return "", []

    ordered = sorted(chars, key=lambda c: (round(c.get("top", 0.0), 2), c.get("x0", 0.0)))
    parts: list[str] = []
    index_map: list[dict[str, Any] | None] = []
    previous: dict[str, Any] | None = None

    for char in ordered:
        if previous is not None:
            prev_bottom = previous.get("bottom", previous.get("top", 0.0))
            line_break = abs(char.get("top", 0.0) - previous.get("top", 0.0)) > max(
                3.0, (prev_bottom - previous.get("top", 0.0)) * 0.8)
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
    ordered = sorted(chars, key=lambda c: (round(c.get("top", 0.0), 2), c.get("x0", 0.0)))
    lines: list[list[dict[str, Any]]] = [[ordered[0]]]
    for char in ordered[1:]:
        if abs(char.get("top", 0.0) - lines[-1][0].get("top", 0.0)) <= tolerance:
            lines[-1].append(char)
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
    # Tier 1: exact char-index mapping
    matched_chars = [
        index_map[i] for i in range(match_start, min(match_end, len(index_map)))
        if index_map[i] is not None
    ]
    if matched_chars:
        left = min(c["x0"] for c in matched_chars)
        top = min(c["top"] for c in matched_chars)
        right = max(c["x1"] for c in matched_chars)
        bottom = max(c["bottom"] for c in matched_chars)
        bbox = normalize_bbox(left, top, right - left, bottom - top, page_width, page_height)
        if bbox:
            return bbox

    # Tier 2: line-level scan with compact matching
    target = normalize_compact(finding_value)
    if target:
        for line in group_chars_into_lines(chars):
            line_text = "".join(c.get("text", "") for c in line)
            if target in normalize_compact(line_text):
                left = min(c["x0"] for c in line)
                top = min(c["top"] for c in line)
                right = max(c["x1"] for c in line)
                bottom = max(c["bottom"] for c in line)
                bbox = normalize_bbox(left, top, right - left, bottom - top, page_width, page_height)
                if bbox:
                    return bbox

    # Tier 3: multi-line scan (for cross-line values like emails)
    if target:
        lines = group_chars_into_lines(chars)
        for i in range(len(lines)):
            merged_text = ""
            merged_chars: list[dict[str, Any]] = []
            for j in range(i, min(i + 3, len(lines))):
                merged_text += "".join(c.get("text", "") for c in lines[j])
                merged_chars.extend(lines[j])
                if target in normalize_compact(merged_text):
                    left = min(c["x0"] for c in merged_chars)
                    top = min(c["top"] for c in merged_chars)
                    right = max(c["x1"] for c in merged_chars)
                    bottom = max(c["bottom"] for c in merged_chars)
                    bbox = normalize_bbox(left, top, right - left, bottom - top, page_width, page_height)
                    if bbox:
                        return bbox

    return None


# ==========================================================================
# OCR ENGINE + IMAGE PREPROCESSING (unchanged from your working code)
# ==========================================================================

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
    base = ImageOps.exif_transpose(image).convert("RGB")
    if cv2 is None or np is None:
        return ImageOps.autocontrast(base)

    gray = cv2.cvtColor(np.array(base), cv2.COLOR_RGB2GRAY)
    denoised = cv2.fastNlMeansDenoising(gray, None, h=17, templateWindowSize=7, searchWindowSize=21)
    contrast = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(denoised)

    h, w = contrast.shape[:2]
    longest = max(w, h)
    if longest < 1500:
        scale = min(2.0, 1500.0 / longest)
        contrast = cv2.resize(contrast, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    thresh = cv2.adaptiveThreshold(contrast, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 15)
    thresh = cv2.medianBlur(thresh, 3)
    return Image.fromarray(thresh)


def preprocess_image_soft(image: Image.Image) -> Image.Image:
    base = ImageOps.exif_transpose(image).convert("RGB")
    if cv2 is None or np is None:
        return ImageOps.autocontrast(base)

    gray = cv2.cvtColor(np.array(base), cv2.COLOR_RGB2GRAY)
    contrast = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)

    h, w = contrast.shape[:2]
    longest = max(w, h)
    if longest < 1400:
        scale = min(2.0, 1400.0 / longest)
        contrast = cv2.resize(contrast, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    return Image.fromarray(contrast)


def snap_orientation_angle(angle: int) -> int:
    n = angle % 360
    return min((0, 90, 180, 270), key=lambda c: min(abs(c - n), 360 - abs(c - n)))


def parse_osd_orientation(osd_text: str) -> dict[str, Any]:
    angle = 0
    confidence = 0.0
    for line in osd_text.splitlines():
        if line.startswith("Orientation in degrees:"):
            angle = snap_orientation_angle(safe_int(line.split(":", 1)[1].strip()))
        elif line.startswith("Orientation confidence:"):
            confidence = max(0.0, min(1.0, safe_float(line.split(":", 1)[1].strip(), 0.0) / 10.0))
    return {"angle": angle, "confidence": round(confidence, 2), "method": "osd"}


def reduced_for_orientation(image: Image.Image, max_side: int = 1000) -> Image.Image:
    working = ImageOps.exif_transpose(image).convert("RGB")
    longest = max(working.size)
    if longest <= max_side:
        return working
    scale = max_side / longest
    return working.resize(
        (max(1, int(working.width * scale)), max(1, int(working.height * scale))),
        Image.Resampling.LANCZOS,
    )


def score_orientation_image(image: Image.Image) -> float:
    try:
        processed = preprocess_image_soft(image)
        _, words = ocr_words_from_image(processed)
        return score_ocr_words(words)
    except Exception:
        return -1.0


def detect_orientation(image: Image.Image) -> dict[str, Any]:
    working = reduced_for_orientation(image)
    try:
        osd = pytesseract.image_to_osd(working)
        orientation = parse_osd_orientation(osd)
        if orientation["confidence"] > 0:
            return orientation
    except Exception:
        pass

    scores: dict[int, float] = {}
    for angle in (0, 90, 180, 270):
        candidate = working if angle == 0 else working.rotate(-angle, expand=True)
        scores[angle] = score_orientation_image(candidate)

    best = max(scores, key=scores.get)
    best_score = scores[best]
    if best_score <= 0:
        return {"angle": 0, "confidence": 0.0, "method": "none"}

    ordered = sorted(scores.values(), reverse=True)
    runner = ordered[1] if len(ordered) > 1 else 0.0
    conf = min(1.0, max(0.1, (best_score - runner) / max(best_score, 1.0)))
    return {"angle": best, "confidence": round(conf, 2), "method": "sweep"}


def correct_orientation(image: Image.Image, angle: int) -> Image.Image:
    base = ImageOps.exif_transpose(image).convert("RGB")
    n = snap_orientation_angle(angle)
    return base if n == 0 else base.rotate(-n, expand=True)


def prepare_ocr_display_image(image: Image.Image) -> tuple[Image.Image, dict[str, Any]]:
    base = ImageOps.exif_transpose(image).convert("RGB")
    orientation = detect_orientation(base)
    return correct_orientation(base, orientation["angle"]), orientation


# ==========================================================================
# OCR WORD EXTRACTION
# ==========================================================================

def score_ocr_words(words: list[dict[str, Any]]) -> float:
    if not words:
        return -1.0
    confs = [max(w.get("conf", -1.0), 0.0) for w in words]
    avg = sum(confs) / max(len(confs), 1)
    alnums = sum(sum(c.isalnum() for c in w["text"]) for w in words)
    return avg + min(alnums, 80)


def build_ocr_words(ocr_data: dict[str, list[Any]]) -> tuple[str, list[dict[str, Any]]]:
    words: list[dict[str, Any]] = []
    parts: list[str] = []
    cursor = 0
    line_order: dict[tuple[int, int, int], int] = {}

    for i, raw_word in enumerate(ocr_data.get("text", [])):
        word = raw_word.strip()
        if not word:
            continue

        start = cursor + (1 if parts else 0)
        if parts:
            cursor += 1
        parts.append(word)
        end = start + len(word)
        cursor = end

        lk = (
            safe_int(ocr_data.get("block_num", [0])[i]),
            safe_int(ocr_data.get("par_num", [0])[i]),
            safe_int(ocr_data.get("line_num", [0])[i]),
        )
        if lk not in line_order:
            line_order[lk] = len(line_order)

        words.append({
            "text": word,
            "left": float(ocr_data["left"][i]),
            "top": float(ocr_data["top"][i]),
            "width": float(ocr_data["width"][i]),
            "height": float(ocr_data["height"][i]),
            "start": start,
            "end": end,
            "conf": safe_float(ocr_data.get("conf", ["-1"])[i]),
            "block_num": lk[0],
            "par_num": lk[1],
            "line_num": lk[2],
            "line_index": line_order[lk],
        })

    return " ".join(parts), words


def ocr_words_from_image(image: Image.Image) -> tuple[str, list[dict[str, Any]]]:
    ocr_data = pytesseract.image_to_data(image, output_type=Output.DICT, config=OCR_CONFIG)
    return build_ocr_words(ocr_data)


def ocr_image_page(image: Image.Image, page_number: int, prepared: bool = False) -> dict[str, Any]:
    if prepared:
        display = ImageOps.exif_transpose(image).convert("RGB")
        orientation = {"angle": 0, "confidence": 1.0, "method": "precorrected"}
    else:
        display, orientation = prepare_ocr_display_image(image)

    primary = preprocess_image(display)
    text, words = ocr_words_from_image(primary)

    if score_ocr_words(words) < 55:
        fallback = preprocess_image_soft(display)
        fb_text, fb_words = ocr_words_from_image(fallback)
        if score_ocr_words(fb_words) > score_ocr_words(words):
            primary = fallback
            text = fb_text
            words = fb_words

    return {
        "page_number": page_number,
        "text": text,
        "ocr_words": words,
        "width": float(primary.width),
        "height": float(primary.height),
        "rotation_applied": orientation["angle"],
        "_display_image": display,
    }


# ==========================================================================
# PAGE EXTRACTION + PREVIEW
# ==========================================================================

def extract_pdf_pages(file_bytes: bytes) -> list[dict[str, Any]]:
    pages: list[dict[str, Any]] = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for pn, page in enumerate(pdf.pages, 1):
            chars = page.chars or []
            text, idx_map = add_spacing_between_chars(chars)
            pages.append({
                "page_number": pn,
                "text": text,
                "chars": chars,
                "index_map": idx_map,
                "width": float(page.width),
                "height": float(page.height),
            })
    return pages


def extract_image_pages(file_bytes: bytes, file_type: str) -> list[dict[str, Any]]:
    if not ocr_is_available():
        raise ValueError("OCR engine unavailable")
    if file_type == "pdf":
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        try:
            pages = []
            for i, page in enumerate(doc, 1):
                pix = page.get_pixmap(alpha=False)
                img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
                p = ocr_image_page(img, i)
                p.pop("_display_image", None)
                pages.append(p)
            return pages
        finally:
            doc.close()
    img = Image.open(io.BytesIO(file_bytes)).convert("RGB")
    p = ocr_image_page(img, 1)
    p.pop("_display_image", None)
    return [p]


def extract_image_pages_with_previews(
    file_bytes: bytes, file_type: str,
) -> tuple[list[dict[str, Any]], int, list[dict[str, Any]]]:
    if not ocr_is_available():
        raise ValueError("OCR engine unavailable")

    if file_type == "pdf":
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        try:
            pc = doc.page_count
            payloads, previews = [], []
            for i in range(min(pc, MAX_RASTER_PAGES)):
                page = doc.load_page(i)
                pix = page.get_pixmap(alpha=False)
                img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
                p = ocr_image_page(img, i + 1)
                disp = p.pop("_display_image")
                payloads.append(p)
                previews.append({"page_number": i + 1, **encode_preview_image(disp)})
            return payloads, pc, previews
        finally:
            doc.close()

    img = Image.open(io.BytesIO(file_bytes)).convert("RGB")
    p = ocr_image_page(img, 1)
    disp = p.pop("_display_image")
    return [p], 1, [{"page_number": 1, **encode_preview_image(disp)}]


def encode_preview_image(image: Image.Image) -> dict[str, Any]:
    preview = ImageOps.exif_transpose(image).convert("RGB")
    w, h = preview.size
    if w > MAX_PREVIEW_WIDTH:
        ratio = MAX_PREVIEW_WIDTH / w
        preview = preview.resize((MAX_PREVIEW_WIDTH, max(1, int(h * ratio))), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    preview.save(buf, format="PNG")
    return {"image_b64": base64.b64encode(buf.getvalue()).decode("ascii"), "width": preview.width, "height": preview.height}


def extract_pdf_ocr_pages_with_previews(
    file_bytes: bytes,
) -> tuple[list[dict[str, Any]], int, list[dict[str, Any]]]:
    if not ocr_is_available():
        raise ValueError("OCR engine unavailable")
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    try:
        pc = doc.page_count
        payloads, previews = [], []
        for i in range(min(pc, MAX_RASTER_PAGES)):
            page = doc.load_page(i)
            pix = page.get_pixmap(alpha=False)
            img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
            disp, orient = prepare_ocr_display_image(img)
            p = ocr_image_page(disp, i + 1, prepared=True)
            p.pop("_display_image", None)
            p["rotation_applied"] = orient["angle"]
            payloads.append(p)
            previews.append({"page_number": i + 1, **encode_preview_image(disp)})
        return payloads, pc, previews
    finally:
        doc.close()


# ==========================================================================
# FUZZY OCR DETECTION — sliding windows over spatial tokens
# ==========================================================================

def iter_ocr_windows(ocr_words: list[dict[str, Any]], max_window: int = 6) -> list[list[dict[str, Any]]]:
    windows = []
    total = len(ocr_words)
    for start in range(total):
        current = []
        base = ocr_words[start]
        for end in range(start, min(total, start + max_window)):
            w = ocr_words[end]
            if w["line_index"] - base["line_index"] > 1:
                break
            vspan = (w["top"] + w["height"]) - base["top"]
            if vspan > max(base["height"], w["height"]) * 4.0:
                break
            current.append(w)
            windows.append(list(current))
    return windows


def detect_pan_from_words(words: list[dict[str, Any]]) -> dict[str, Any] | None:
    window_text = " ".join(w["text"] for w in words)
    compact = re.sub(r"[^A-Za-z0-9]", "", normalize_text(window_text).upper())
    if len(compact) < 10:
        return None

    best_val, best_score, best_reason, best_status = None, 0.0, "", ""

    for idx in range(0, len(compact) - 9):
        frag = compact[idx:idx + 10]
        repaired, reps = repair_pan_fragment(frag)
        if not repaired:
            continue

        score = max(0.72, 0.93 - reps * 0.08)
        ctx = 0.0
        reason = "Fuzzy OCR match"
        full = window_text.upper()

        if any(kw in full for kw in PAN_POSITIVE_CONTEXT):
            ctx += 0.2
            reason = "Fuzzy + context"
        if any(kw in full for kw in PAN_NEGATIVE_CONTEXT):
            ctx -= 0.4
            reason = "Fuzzy - negative context"

        # Spatial: bottom-of-page penalty
        avg_y = sum(w["top"] + w["height"] / 2 for w in words) / len(words)
        if avg_y > 0.8:
            ctx -= 0.15

        final = score + ctx
        if final > best_score:
            best_val, best_score, best_reason = repaired, final, reason

    if not best_val or best_score < 0.5:
        return None

    status = "detected" if best_score > 0.85 else "review"
    return {
        "type": "pan", "raw_value": best_val,
        "confidence": round(min(0.99, best_score), 2),
        "matched_words": words, "status": status, "reason": best_reason,
    }


def detect_phone_from_words(words: list[dict[str, Any]]) -> dict[str, Any] | None:
    window_text = " ".join(w["text"] for w in words)
    if "@" in window_text:
        return None

    digits = re.sub(r"\D", "", normalize_text(window_text))
    if len(digits) < 10:
        return None

    # Extract candidate
    phone = None
    base_score = 0.0
    if len(digits) == 10 and digits[0] in "6789":
        phone, base_score = digits, 0.9
    elif len(digits) == 11 and digits[0] == "0" and digits[1] in "6789":
        phone, base_score = digits[1:11], 0.87
    elif len(digits) == 12 and digits[:2] == "91" and digits[2] in "6789":
        phone, base_score = digits[2:12], 0.88

    if not phone:
        return None

    val_score, _ = validate_phone(phone, window_text)
    if val_score == 0.0:
        return None

    return {
        "type": "phone", "raw_value": phone,
        "confidence": round(min(base_score, val_score), 2),
        "matched_words": words,
    }


def detect_aadhaar_from_words(words: list[dict[str, Any]]) -> dict[str, Any] | None:
    window_text = " ".join(w["text"] for w in words)
    digits = re.sub(r"\D", "", normalize_text(window_text))
    if len(digits) < 12:
        return None

    grouped = bool(re.search(r"[2-9][0-9OIlS]{3}\s+[0-9OIlS]{4}\s+[0-9OIlS]{4}", window_text))
    best_frag, best_score = None, 0.0

    for i in range(0, len(digits) - 11):
        frag = digits[i:i + 12]
        score, _ = validate_aadhaar(frag)
        if score == 0.0:
            continue
        if grouped:
            score = min(score + 0.04, 0.97)
        if score > best_score:
            best_frag, best_score = frag, score

    if not best_frag:
        return None

    formatted = f"{best_frag[0:4]} {best_frag[4:8]} {best_frag[8:12]}"
    return {
        "type": "aadhaar", "raw_value": formatted,
        "confidence": round(best_score, 2),
        "matched_words": words,
    }


def detect_email_from_words(words: list[dict[str, Any]]) -> dict[str, Any] | None:
    # Also try merging adjacent lines for cross-line emails
    window_text = " ".join(w["text"] for w in words)
    norm = normalize_email_text(window_text)
    if "@" not in norm:
        return None

    match = EMAIL_RELAXED_RE.search(norm)
    if not match:
        return None

    candidate = match.group(0)
    val_score, _ = validate_email(candidate)
    if val_score == 0.0:
        return None

    repair_cost = abs(len(re.sub(r"\s+", "", window_text)) - len(candidate))
    ocr_score = max(0.72, 0.9 - repair_cost * 0.03)
    final = min(ocr_score, val_score)

    return {
        "type": "email", "raw_value": candidate,
        "confidence": round(final, 2),
        "matched_words": words,
    }


FUZZY_DETECTORS = (
    detect_pan_from_words,
    detect_phone_from_words,
    detect_email_from_words,
    detect_aadhaar_from_words,
)


# ==========================================================================
# FINDING BUILDER
# ==========================================================================

def build_finding(
    pii_type: str, raw_value: str, page_number: int,
    confidence: float, bbox: dict[str, float] | None,
    status: str = "detected", reason: str = "Regex match",
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
        "status": status,
        "reason": reason,
    }


# ==========================================================================
# CROSS-TYPE COLLISION PREVENTION
# ==========================================================================

def is_aadhaar_substring(phone_digits: str, aadhaar_set: set[str]) -> bool:
    for a in aadhaar_set:
        if phone_digits in a:
            return True
    return False


def is_phone_overlapping_pan(phone_digits: str, pan_set: set[str]) -> bool:
    """Check if 4-digit suffix of phone overlaps with PAN numeric portion."""
    for pan in pan_set:
        if len(pan) == 10 and phone_digits == pan[5:9] + pan[9]:
            return True
    return False


# ==========================================================================
# COLLECTION PIPELINE — separated into clear stages
# ==========================================================================

def _pre_scan_aadhaar(page_payloads: list[dict[str, Any]]) -> dict[int, set[str]]:
    """Pass 0: Pre-scan all Aadhaar candidates on every page for cross-type dedup."""
    result: dict[int, set[str]] = defaultdict(set)

    for pp in page_payloads:
        text = pp["text"]
        if not text:
            continue
        pn = pp["page_number"]

        # Spaced Aadhaar
        for m in re.finditer(PII_PATTERNS["aadhaar"], text):
            d = re.sub(r"\D", "", m.group())
            score, _ = validate_aadhaar(d)
            if score > 0:
                result[pn].add(d)

        # Continuous Aadhaar
        normed = normalize_text(text)
        for m in AADHAAR_CONTINUOUS_RE.finditer(normed):
            d = m.group()
            score, _ = validate_aadhaar(d)
            if score > 0:
                result[pn].add(d)

    return result


def _detect_exact(
    page_payloads: list[dict[str, Any]],
    mode: str,
    aadhaar_pre: dict[int, set[str]],
) -> tuple[list[dict[str, Any]], set[tuple[str, int, str]]]:
    """Stage 1: Strict regex detection with validation."""
    findings: list[dict[str, Any]] = []
    seen: set[tuple[str, int, str]] = set()

    for pp in page_payloads:
        text = pp["text"]
        if not text:
            continue
        pn = pp["page_number"]
        page_aadhaar = aadhaar_pre.get(pn, set())

        for pii_type, pattern in PII_PATTERNS.items():
            for match in re.finditer(pattern, text):
                raw = match.group()
                canon = canonical_value(pii_type, raw)
                dk = (pii_type, pn, canon)
                if dk in seen:
                    continue

                # --- VALIDATE ---
                if pii_type == "aadhaar":
                    digits = re.sub(r"\D", "", raw)
                    score, reason = validate_aadhaar(digits)
                    if score == 0.0:
                        continue
                    confidence = score
                    status = "detected" if score >= 0.7 else "review"

                elif pii_type == "pan":
                    repaired, _ = repair_pan_fragment(raw)
                    if not repaired:
                        continue
                    confidence, reason = validate_pan(repaired, text)
                    if confidence == 0.0:
                        continue
                    status = "detected" if confidence >= 0.7 else "review"

                elif pii_type == "phone":
                    digits = re.sub(r"\D", "", raw)
                    phone_d = digits[-10:] if len(digits) >= 10 else digits
                    if is_aadhaar_substring(phone_d, page_aadhaar):
                        continue
                    confidence, reason = validate_phone(phone_d, text)
                    if confidence == 0.0:
                        continue
                    status = "detected"

                elif pii_type == "email":
                    confidence, reason = validate_email(raw)
                    if confidence == 0.0:
                        continue
                    status = "detected"
                else:
                    confidence, reason, status = 0.9, "Regex match", "detected"

                seen.add(dk)

                # --- MAP BBOX ---
                if mode == "pdf_text":
                    bbox = map_pdf_bbox(
                        raw, match.start(), match.end(),
                        pp["index_map"], pp["chars"], pp["width"], pp["height"],
                    )
                else:
                    bbox = map_ocr_bbox(
                        raw, match.start(), match.end(),
                        pp["ocr_words"], pp["width"], pp["height"],
                    )
                    confidence = min(confidence, 0.88)

                findings.append(build_finding(pii_type, raw, pn, confidence, bbox, status, reason))

        # --- Continuous Aadhaar (supplementary) ---
        normed = normalize_text(text)
        for match in AADHAAR_CONTINUOUS_RE.finditer(normed):
            digits = match.group()
            canon = canonical_value("aadhaar", digits)
            dk = ("aadhaar", pn, canon)
            if dk in seen:
                continue

            score, reason = validate_aadhaar(digits)
            if score == 0.0:
                continue

            # Lower confidence for ungrouped
            adj_conf = score * 0.85
            if adj_conf < 0.45:
                continue

            seen.add(dk)
            formatted = f"{digits[0:4]} {digits[4:8]} {digits[8:12]}"
            status = "detected" if verhoeff_checksum(digits) else "review"

            if mode == "pdf_text":
                bbox = map_pdf_bbox(
                    match.group(), match.start(), match.end(),
                    pp["index_map"], pp["chars"], pp["width"], pp["height"],
                )
            else:
                bbox = map_ocr_bbox(
                    match.group(), match.start(), match.end(),
                    pp["ocr_words"], pp["width"], pp["height"],
                )

            findings.append(build_finding("aadhaar", formatted, pn, round(adj_conf, 2), bbox, status, reason))

    return findings, seen


def _detect_fuzzy_ocr(
    page_payloads: list[dict[str, Any]],
    seen: set[tuple[str, int, str]],
    aadhaar_pre: dict[int, set[str]],
) -> list[dict[str, Any]]:
    """Stage 2: Fuzzy sliding-window detection for OCR images."""
    findings: list[dict[str, Any]] = []

    # Build mutable aadhaar tracking (fuzzy may discover new ones)
    live_aadhaar: dict[int, set[str]] = defaultdict(set)
    for pn, vals in aadhaar_pre.items():
        live_aadhaar[pn] = set(vals)
    for key in seen:
        if key[0] == "aadhaar":
            live_aadhaar[key[1]].add(key[2])

    for pp in page_payloads:
        pn = pp["page_number"]
        page_aadh = live_aadhaar.get(pn, set())
        windows = iter_ocr_windows(pp["ocr_words"])
        per_type_best: dict[tuple[str, str], dict[str, Any]] = {}

        for window in windows:
            for detector in FUZZY_DETECTORS:
                det = detector(window)
                if not det:
                    continue

                pt = det["type"]
                canon = canonical_value(pt, det["raw_value"])
                dk = (pt, pn, canon)
                if dk in seen:
                    continue

                # Cross-type phone check
                if pt == "phone":
                    pd = re.sub(r"\D", "", det["raw_value"])[-10:]
                    if is_aadhaar_substring(pd, page_aadh):
                        continue

                rk = (pt, canon)
                existing = per_type_best.get(rk)
                if existing is None or det["confidence"] > existing["confidence"]:
                    per_type_best[rk] = det

        for det in per_type_best.values():
            pt = det["type"]
            canon = canonical_value(pt, det["raw_value"])
            dk = (pt, pn, canon)
            if dk in seen:
                continue
            seen.add(dk)

            if pt == "aadhaar":
                d = re.sub(r"\D", "", det["raw_value"])
                live_aadhaar.setdefault(pn, set()).add(d)

            bbox = union_word_boxes(det["matched_words"], pp["width"], pp["height"])
            findings.append(build_finding(
                pt, det["raw_value"], pn,
                det["confidence"], bbox,
                det.get("status", "detected"),
                det.get("reason", "Fuzzy OCR match"),
            ))

    return findings


def _final_dedup(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Stage 3: Final cross-type collision removal."""
    # Collect all Aadhaar digits by page
    aadhaar_by_page: dict[int, set[str]] = defaultdict(set)
    for f in findings:
        if f["type"] == "aadhaar":
            aadhaar_by_page[f["page"]].add(re.sub(r"\D", "", f["raw_value"]))

    cleaned = []
    for f in findings:
        if f["type"] == "phone":
            pd = re.sub(r"\D", "", f["raw_value"])[-10:]
            if is_aadhaar_substring(pd, aadhaar_by_page.get(f["page"], set())):
                continue
        cleaned.append(f)

    cleaned.sort(key=lambda x: (x["page"], x["type"], canonical_value(x["type"], x["raw_value"])))
    return cleaned


def collect_regex_findings(page_payloads: list[dict[str, Any]], mode: str) -> list[dict[str, Any]]:
    """Main entry: orchestrates the 3-stage pipeline."""
    aadhaar_pre = _pre_scan_aadhaar(page_payloads)
    findings, seen = _detect_exact(page_payloads, mode, aadhaar_pre)
    if mode == "ocr_image":
        findings.extend(_detect_fuzzy_ocr(page_payloads, seen, aadhaar_pre))
    return _final_dedup(findings)


# ==========================================================================
# PREVIEW + REDACTION (unchanged API contract)
# ==========================================================================

def build_pdf_previews(file_bytes: bytes) -> tuple[int, list[dict[str, Any]]]:
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    try:
        pc = doc.page_count
        previews = []
        for i in range(min(pc, MAX_RASTER_PAGES)):
            page = doc.load_page(i)
            previews.append({"page_number": i + 1, **render_pdf_page_preview(page)})
        return pc, previews
    finally:
        doc.close()


def render_pdf_page_preview(page: fitz.Page) -> dict[str, Any]:
    rect = page.rect
    scale = max(0.5, min(MAX_PREVIEW_WIDTH / rect.width, 2.0))
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
    return {
        "image_b64": base64.b64encode(pix.tobytes("png")).decode("ascii"),
        "width": pix.width, "height": pix.height,
    }


def build_image_previews(file_bytes: bytes) -> tuple[int, list[dict[str, Any]]]:
    img = Image.open(io.BytesIO(file_bytes)).convert("RGB")
    disp, _ = prepare_ocr_display_image(img)
    return 1, [{"page_number": 1, **encode_preview_image(disp)}]


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
    for c in candidates:
        if c and os.path.exists(c):
            pytesseract.pytesseract.tesseract_cmd = c
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
    for ft, magic in MAGIC_BYTES.items():
        if file_bytes.startswith(magic):
            return ft
    return None


def file_hash(file_bytes: bytes) -> str:
    return hashlib.sha256(file_bytes).hexdigest()


def cache_findings(digest: str, findings: list[dict[str, Any]], mode: str) -> None:
    for key in [k for k in scan_cache if k[0] == digest]:
        scan_cache.pop(key, None)
    for f in findings:
        scan_cache[(digest, f["id"])] = {"page": f["page"], "bbox": f["bbox"], "mode": mode}


def render_redacted_pdf(file_bytes: bytes, file_type: str, finding_ids: list[str]) -> bytes:
    digest = file_hash(file_bytes)
    cached = {k for k in scan_cache if k[0] == digest}
    if not cached:
        raise LookupError("file_mismatch")

    entries = []
    for fid in finding_ids:
        ck = (digest, fid)
        if ck not in scan_cache:
            raise KeyError("invalid_finding_ids")
        entries.append(scan_cache[ck])

    by_page: dict[int, list[dict[str, Any] | None]] = defaultdict(list)
    for e in entries:
        by_page[e["page"]].append(e["bbox"])

    render_mode = entries[0].get("mode") if entries else None
    output = fitz.open()

    if file_type == "pdf":
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        try:
            for i in range(doc.page_count):
                page = doc.load_page(i)
                pix = page.get_pixmap(alpha=False)
                img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
                if render_mode == "ocr_image":
                    img, _ = prepare_ocr_display_image(img)
                draw_redactions(img, by_page.get(i + 1, []))
                append_image_page(output, img)
        finally:
            doc.close()
    else:
        img = Image.open(io.BytesIO(file_bytes)).convert("RGB")
        img, _ = prepare_ocr_display_image(img)
        draw_redactions(img, by_page.get(1, []))
        append_image_page(output, img)

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
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    page = document.new_page(width=image.width, height=image.height)
    page.insert_image(page.rect, stream=buf.getvalue())


async def read_upload_file(file: UploadFile) -> tuple[bytes, str]:
    fb = await file.read()
    if len(fb) > MAX_FILE_SIZE:
        raise ValueError("file_too_large")
    detected = detect_file_type(fb)
    if detected is None:
        raise TypeError("unsupported_file_type")
    return fb, detected


# ==========================================================================
# ENDPOINTS — identical API contract, no CORS changes
# ==========================================================================

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
    return {"status": "ok", "ocr_available": ocr_is_available(), "version": APP_VERSION}


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
            joined = "".join(p["text"] for p in page_payloads).strip()
            if joined:
                mode = "pdf_text"
                page_count, pages = build_pdf_previews(file_bytes)
            else:
                mode = "ocr_image"
                page_payloads, page_count, pages = extract_pdf_ocr_pages_with_previews(file_bytes)
        else:
            page_payloads, page_count, pages = extract_image_pages_with_previews(file_bytes, detected_type)
            mode = "ocr_image"

        findings = collect_regex_findings(page_payloads, mode)
        if mode == "ocr_image" and not "".join(p["text"] for p in page_payloads).strip():
            return error_response(400, "no_text_extracted")

        cache_findings(file_hash(file_bytes), findings, mode)
        return JSONResponse(content={
            "mode": mode,
            "page_count": page_count,
            "pages": pages,
            "findings": findings,
            "risk_score": build_risk_score(findings),
        })
    except ValueError:
        logger.warning("Scan returned no_text_extracted for %s (%s). OCR: %s",
                        file.filename or "upload", detected_type, ocr_is_available())
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
        if not isinstance(parsed_ids, list) or not all(isinstance(x, str) for x in parsed_ids):
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
