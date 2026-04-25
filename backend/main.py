import base64
import hashlib
import io
import json
import logging
import re
import uuid
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

import fitz  # PyMuPDF
import pdfplumber
import pytesseract
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from PIL import Image, ImageDraw, ImageOps, ImageEnhance, ImageFilter
from pytesseract import Output

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pii_shield")

# --- Constants & Configuration (Per agents.md) ---
APP_VERSION = "1.0.0"
MAX_FILE_SIZE = 10 * 1024 * 1024
MAX_RASTER_PAGES = 3
MAX_PREVIEW_WIDTH = 1000

# Canonical Regex Patterns
# Updated pattern to allow '0' or '1' as the starting digit for testing
PII_PATTERNS = {
    "aadhaar": r"\b[0-9]{4}\s[0-9]{4}\s[0-9]{4}\b", 
    "pan":     r"\b[A-Z]{5}[0-9]{4}[A-Z]{1}\b",
    "voter_id": r"\b[A-Z]{3}[0-9]{7}\b",
    "phone":   r"\b(?:\+91[\-\s]?)?[6-9]\d{9}\b",
    "email":   r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b",
    "ean_13":  r"\b\d{13}\b",      # Standard 13-digit Barcode
    "upc_a":   r"\b\d{12}\b"

}

# 1. Step 2: Validation Patterns (Already in your PII_PATTERNS)
BARCODE_VALIDATORS = {
    "ean_13": r"^\d{13}$",
    "upc_a": r"^\d{12}$",
    "qr_code": r".+" # QRs can be any string, but we validate existence
}

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

SEVERITY_MAP = {
    "aadhaar": "high",
    "pan":     "high",
    "voter_id": "high",
    "phone":   "medium",
    "email":   "medium",
    "ean_13": "medium",
    "upc_a": "medium"
}

# Application Init
app = FastAPI(title="PII Shield MVP", version=APP_VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global in-memory cache keyed by (file_hash, finding_id)
scan_cache: Dict[Tuple[str, str], Dict[str, Any]] = {}

# --- Helper Functions ---

def is_ocr_available() -> bool:
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False

def file_hash(file_bytes: bytes) -> str:
    return hashlib.sha256(file_bytes).hexdigest()

def mask_value(pii_type: str, raw: str) -> str:
    """Masks PII values for safe frontend display."""
    if pii_type == "aadhaar":
        return f"XXXX-XXXX-{raw[-4:]}"
    if pii_type == "pan":
        return f"XXXXX{raw[5:9]}X"
    if pii_type == "voter_id":
        return f"{raw[:3]}XXXXXXX"
    if pii_type == "phone":
        clean = re.sub(r'\D', '', raw)
        return f"XXXXXX{clean[-4:]}"
    if pii_type == "email":
        local, domain = raw.split("@", 1)
        return f"{local[0]}***@{domain}"
    return "XXXX"

def preprocess_image(img: Image.Image) -> Image.Image:
    """Preprocessor: Autocontrast and Sharpening to help OCR."""
    img = ImageOps.autocontrast(img.convert("RGB"))
    return img.filter(ImageFilter.SHARPEN) # Helps OCR see barcode numbers better

def encode_preview(img: Image.Image) -> str:
    """Resizes and encodes rasterized page to base64."""
    if img.width > MAX_PREVIEW_WIDTH:
        ratio = MAX_PREVIEW_WIDTH / img.width
        img = img.resize((MAX_PREVIEW_WIDTH, int(img.height * ratio)), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")

# --- Bbox Mapper ---

def map_bbox(match_start: int, match_end: int, words: List[Dict], width: float, height: float) -> Optional[Dict[str, float]]:
    """3-Tier BboxMapper Fallback Logic."""
    if not words or width <= 0 or height <= 0:
        return None

    # Tier 1: Exact Char mapping
    covered = [w for w in words if w["start"] < match_end and w["end"] > match_start]
    
    # Tier 2: Word/Line mapping (If exact char fails, fallback to line approx)
    if not covered:
        # Fallback to checking words around the index
        closest_words = [w for w in words if abs(w["start"] - match_start) < 50]
        if closest_words:
            covered = closest_words[:1]

    if covered:
        left = min(w["left"] for w in covered)
        top = min(w["top"] for w in covered)
        right = max(w["left"] + w["width"] for w in covered)
        bottom = max(w["top"] + w["height"] for w in covered)
        
        # Normalize to 0.0 - 1.0 floats
        return {
            "x": max(0.0, min(1.0, left / width)),
            "y": max(0.0, min(1.0, top / height)),
            "w": max(0.0, min(1.0, (right - left) / width)),
            "h": max(0.0, min(1.0, (bottom - top) / height))
        }

    # Tier 3: Null Fallback
    return None

# --- API Endpoints ---

@app.get("/health")
def health():
    return {
        "status": "ok",
        "ocr_available": is_ocr_available(),
        "version": APP_VERSION
    }
@app.post("/scan")
async def scan(file: UploadFile = File(...)):
    """Scans the uploaded document for PII using regex and OCR."""
    try:
        file_bytes = await file.read()
        
        if len(file_bytes) > MAX_FILE_SIZE:
            logger.warning(f"Rejected file: Size is over {MAX_FILE_SIZE} bytes")
            return JSONResponse({"error": "file_too_large"}, status_code=400)
            
        digest = file_hash(file_bytes)
        filename = file.filename.lower()
        is_pdf = filename.endswith(".pdf")
        mode = "pdf_text" if is_pdf else "ocr_image"

        page_payloads = []
        pages_output = []
        
        # 1. Extraction Phase
        if is_pdf:
            with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                doc = fitz.open(stream=file_bytes, filetype="pdf")
                for i in range(min(len(pdf.pages), MAX_RASTER_PAGES)):
                    page = pdf.pages[i]
                    text = page.extract_text() or ""
                    
                    # Approximate words with coords
                    words = []
                    cursor = 0
                    for ew in page.extract_words():
                        start = text.find(ew["text"], cursor)
                        if start == -1: start = cursor
                        end = start + len(ew["text"])
                        cursor = end
                        words.append({
                            "text": ew["text"], "start": start, "end": end,
                            "left": float(ew["x0"]), "top": float(ew["top"]),
                            "width": float(ew["x1"] - ew["x0"]), "height": float(ew["bottom"] - ew["top"])
                        })
                    
                    page_payloads.append({"page_number": i + 1, "text": text, "words": words, "w": page.width, "h": page.height})
                    
                    # Rasterize for UI
                    pix = doc.load_page(i).get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
                    img = Image.open(io.BytesIO(pix.tobytes("png")))
                    pages_output.append({
                        "page_number": i + 1,
                        "image_b64": encode_preview(img),
                        "width": img.width, "height": img.height
                    })
        else:
            if not is_ocr_available():
                # Better status code for service unavailable
                return JSONResponse(
                    {"error": "ocr_not_available", "detail": "Tesseract OCR is not configured."}, 
                    status_code=503
                )
                
            try:
                img = preprocess_image(Image.open(io.BytesIO(file_bytes)))
                ocr_data = pytesseract.image_to_data(img, output_type=Output.DICT)
            except pytesseract.TesseractError as t_err:
                logger.error(f"Tesseract OCR Engine Error: {t_err}")
                # 422 Unprocessable Entity is perfect for engine failures
                return JSONResponse(
                    {"error": "ocr_engine_failed", "detail": "The OCR engine failed to process the image. It may be corrupted or unsupported."}, 
                    status_code=422
                )
            except Exception as e:
                logger.error(f"Image preprocessing or OCR extraction failed: {e}")
                # 400 Bad Request for unreadable files
                return JSONResponse(
                    {"error": "image_processing_failed", "detail": "Could not read the provided image file."}, 
                    status_code=400
                )
            
            words, text_parts, cursor = [], [], 0
            for i, w in enumerate(ocr_data.get("text", [])):
                if not w.strip(): continue
                start = cursor + (1 if text_parts else 0)
                text_parts.append(w.strip())
                end = start + len(w.strip())
                cursor = end
                words.append({
                    "text": w.strip(), "start": start, "end": end,
                    "left": float(ocr_data["left"][i]), "top": float(ocr_data["top"][i]),
                    "width": float(ocr_data["width"][i]), "height": float(ocr_data["height"][i])
                })
                
            text = " ".join(text_parts)
            if not text.strip():
                logger.warning(f"Rejected image: Tesseract found 0 readable words.")
                return JSONResponse({"error": "no_text_extracted", "detail": "No readable text found in the image."}, status_code=400)

            page_payloads.append({"page_number": 1, "text": text, "words": words, "w": img.width, "h": img.height})
            pages_output.append({
                "page_number": 1,
                "image_b64": encode_preview(img),
                "width": img.width, "height": img.height
            })

        # 2. PII Engine & Detection
        findings = []
        for pp in page_payloads:
            for pii_type, pattern in PII_PATTERNS.items():
                for match in re.finditer(pattern, pp["text"]):
                    finding_id = str(uuid.uuid4())
                    raw_val = match.group()
                    bbox = map_bbox(match.start(), match.end(), pp["words"], pp["w"], pp["h"])
                    
                    finding = {
                        "id": finding_id,
                        "type": pii_type,
                        "value": mask_value(pii_type, raw_val),
                        "raw_value": raw_val,
                        "page": pp["page_number"],
                        "severity": SEVERITY_MAP[pii_type],
                        "confidence": 0.95,
                        "bbox": bbox
                    }
                    findings.append(finding)
                    # Cache raw coords for redaction
                    scan_cache[(digest, finding_id)] = {"page": pp["page_number"], "bbox": bbox}

        # 3. ADVANCED: Barcode/QR Detection (Resilient Engine + Validation)
        try:
            import zxingcpp
            import cv2
            import numpy as np

            scan_targets = []
            if not is_pdf:
                # Use the ORIGINAL high-res bytes here
                img_original = Image.open(io.BytesIO(file_bytes)).convert('RGB')
                scan_targets.append((1, img_original))
            else:
                for page_data in pages_output:
                    img_bytes = base64.b64decode(page_data["image_b64"])
                    scan_targets.append((page_data["page_number"], Image.open(io.BytesIO(img_bytes)).convert('RGB')))

            for page_num, img_target in scan_targets:
                # Convert PIL Image (RGB) to OpenCV format (BGR)
                cv_img = cv2.cvtColor(np.array(img_target), cv2.COLOR_RGB2BGR)
                gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)

                # --- PASS 1: Adaptive Thresholding (Handles shadows and complex backgrounds) ---
                binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                             cv2.THRESH_BINARY, 11, 2)
                
                results = zxingcpp.read_barcodes(binary)
                
                # --- PASS 2: Morphological Dilation (Closes gaps in blurry QR codes) ---
                if not results:
                    kernel = np.ones((3,3), np.uint8)
                    dilated = cv2.dilate(binary, kernel, iterations=1)
                    results = zxingcpp.read_barcodes(dilated)

                # --- PASS 3: Original Image (Last resort) ---
                if not results:
                    results = zxingcpp.read_barcodes(cv_img)

                for result in results:
                    raw_text = result.text
                    
                    # --- VALIDATION/PARSING (Using Regex) ---
                    detected_type = "barcode"
                    
                    if re.match(BARCODE_VALIDATORS["ean_13"], raw_text):
                        detected_type = "ean_13"
                    elif re.match(BARCODE_VALIDATORS["upc_a"], raw_text):
                        detected_type = "upc_a"
                    elif result.format in [zxingcpp.BarcodeFormat.QRCode, zxingcpp.BarcodeFormat.MicroQRCode]:
                        detected_type = "qr_code"

                    finding_id = str(uuid.uuid4())
                    pos = result.position
                    
                    pts = [pos.top_left, pos.top_right, pos.bottom_right, pos.bottom_left]
                    min_x = min(p.x for p in pts)
                    max_x = max(p.x for p in pts)
                    min_y = min(p.y for p in pts)
                    max_y = max(p.y for p in pts)

                    bbox = {
                        "x": max(0.0, min(1.0, min_x / img_target.width)),
                        "y": max(0.0, min(1.0, min_y / img_target.height)),
                        "w": max(0.0, min(1.0, (max_x - min_x) / img_target.width)),
                        "h": max(0.0, min(1.0, (max_y - min_y) / img_target.height))
                    }
                    
                    findings.append({
                        "id": finding_id,
                        "type": detected_type,
                        "value": f"[{detected_type.upper()} REDACTED]",
                        "raw_value": raw_text,
                        "page": page_num,
                        "severity": "high" if detected_type == "qr_code" else "medium",
                        "confidence": 0.99,
                        "bbox": bbox
                    })
                    scan_cache[(digest, finding_id)] = {"page": page_num, "bbox": bbox}

        except Exception as e:
            logger.error(f"Advanced QR Engine failed: {e}")

        high_count = sum(1 for f in findings if f["severity"] == "high")
        med_count = sum(1 for f in findings if f["severity"] == "medium")
        
        return {
            "mode": mode,
            "page_count": len(pages_output),
            "pages": pages_output,
            "findings": findings,
            "risk_score": {
                "level": "HIGH" if high_count > 0 else ("MEDIUM" if med_count > 0 else "SAFE"),
                "total_findings": len(findings),
                "high_count": high_count,
                "medium_count": med_count
            }
        }
        
    except Exception as e:
        logger.exception("Processing failed")
        return JSONResponse({"error": "processing_failed", "detail": str(e)}, status_code=500)


@app.post("/redact")
async def redact(file: UploadFile = File(...), finding_ids: str = Form(...)):
    try:
        file_bytes = await file.read()
        digest = file_hash(file_bytes)
        
        try:
            parsed_ids = json.loads(finding_ids)
        except json.JSONDecodeError:
            return JSONResponse({"error": "invalid_finding_ids"}, status_code=400)

        # Retrieve bboxes from cache
        bboxes_by_page = defaultdict(list)
        for fid in parsed_ids:
            cached = scan_cache.get((digest, fid))
            if cached and cached["bbox"]:
                bboxes_by_page[cached["page"]].append(cached["bbox"])

        output_pdf = fitz.open()

        if file.filename.lower().endswith(".pdf"):
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            for i in range(doc.page_count):
                page = doc.load_page(i)
                # Draw black rectangles using normalized coordinates
                for bbox in bboxes_by_page.get(i + 1, []):
                    rect = fitz.Rect(
                        bbox["x"] * page.rect.width,
                        bbox["y"] * page.rect.height,
                        (bbox["x"] + bbox["w"]) * page.rect.width,
                        (bbox["y"] + bbox["h"]) * page.rect.height
                    )
                    page.draw_rect(rect, color=(0,0,0), fill=(0,0,0))
                output_pdf.insert_pdf(doc, from_page=i, to_page=i)
        else:
            # Redact image and convert to PDF
            img = Image.open(io.BytesIO(file_bytes)).convert("RGB")
            draw = ImageDraw.Draw(img)
            for bbox in bboxes_by_page.get(1, []):
                draw.rectangle([
                    bbox["x"] * img.width,
                    bbox["y"] * img.height,
                    (bbox["x"] + bbox["w"]) * img.width,
                    (bbox["y"] + bbox["h"]) * img.height
                ], fill="black")
            
            buf = io.BytesIO()
            img.save(buf, format="PDF")
            img_pdf = fitz.open(stream=buf.getvalue(), filetype="pdf")
            output_pdf.insert_pdf(img_pdf)

        return Response(
            content=output_pdf.tobytes(),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=redacted_document.pdf"}
        )

    except Exception as e:
        logger.exception("Redaction failed")
        return JSONResponse({"error": "redaction_failed", "detail": str(e)}, status_code=500)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)