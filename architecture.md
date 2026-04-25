# PII Shield — Final Full-Stack Architecture (All Issues Fixed)

> **Project:** Document PII Detection & Redaction Tool  
> **Stack:** React 18 + Vite + Tailwind | FastAPI (single file) | Regex PII Engine  
> **Build Time:** ~6 hours | **Deploy:** Localhost only

---

## 1. System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                      FRONTEND                           │
│  React 18 + Vite + Tailwind                             │
│                                                         │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │ UploadZone  │→ │ DocViewer    │→ │ FindingsPanel│   │
│  │ (drop/pick) │  │ (page imgs + │  │ (list + mask │   │
│  │             │  │  bbox overlay)│  │  toggles)    │   │
│  └─────────────┘  └──────────────┘  └──────────────┘   │
│         │              ▲                    │            │
│         ▼              │                    ▼            │
│  ┌─────────────────────┴────────────────────────┐       │
│  │  useReducer (findings, masks, loading, mode) │       │
│  └──────────────────────────────────────────────┘       │
│         │                                    │          │
│    POST /scan                          POST /redact     │
└─────────┼────────────────────────────────────┼──────────┘
          ▼                                    ▼
┌─────────────────────────────────────────────────────────┐
│                   BACKEND (single main.py)              │
│  FastAPI + uvicorn                                      │
│                                                         │
│  ┌──────────────────────────────────────────────┐       │
│  │  /scan endpoint                              │       │
│  │  1. Detect file type (magic bytes)           │       │
│  │  2. Extract text + coords (PDF or OCR)       │       │
│  │  3. Run PII regex engine                     │       │
│  │  4. Map findings → normalized bboxes         │       │
│  │  5. Rasterize pages → base64 (max 3 pages)  │       │
│  │  6. Return findings + page images            │       │
│  └──────────────────────────────────────────────┘       │
│                                                         │
│  ┌──────────────────────────────────────────────┐       │
│  │  /redact endpoint                            │       │
│  │  1. Receive file + finding_ids               │       │
│  │  2. Look up original bboxes from scan result │       │
│  │  3. Draw black rectangles on rasterized pages│       │
│  │  4. Assemble → return PDF blob               │       │
│  └──────────────────────────────────────────────┘       │
│                                                         │
│  ┌──────────────────────────────────────────────┐       │
│  │  Processing Layer (NO ML)                    │       │
│  │  • PIIEngine: 4 regex patterns               │       │
│  │  • BboxMapper: char-level (PDF), word-level  │       │
│  │    (OCR), with 3-tier fallback               │       │
│  │  • Preprocessor: autocontrast only (fast)    │       │
│  └──────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────┘
```

**Key architectural decisions (with fixes applied):**

- **No session store.** File is re-sent in `/redact`. Eliminates race conditions, TTL cleanup threads, and missing-session bugs entirely.
- **Finding IDs, not raw bboxes**, sent to `/redact`. Backend uses its own computed coordinates — no frontend coordinate drift.
- **Max 3 pages** rendered as base64. Prevents payload bloat and frontend freeze.
- **Normalized bboxes** (0.0–1.0 ratios). Frontend never deals with raw pixel math.
- **3-tier bbox fallback.** Exact → word/line-level → sidebar-only. Demo never shows blank highlights.

---

## 2. Data Flow (Step-by-Step)

```
USER                    FRONTEND                 BACKEND
 │                         │                        │
 │  1. Drops file          │                        │
 │ ───────────────────────>│                        │
 │                         │                        │
 │                    2. Validate                    │
 │                    (type + size < 10MB)           │
 │                         │                        │
 │                    3. POST /scan                  │
 │                    (FormData: file)               │
 │                         │───────────────────────> │
 │                         │                        │
 │                         │   4. Magic-byte detect  │
 │                         │      PDF? → pdfplumber  │
 │                         │        text + chars     │
 │                         │      Image? → OCR       │
 │                         │      Scanned PDF?       │
 │                         │        (empty text →    │
 │                         │         auto-OCR)       │
 │                         │                        │
 │                         │   5. PIIEngine.detect() │
 │                         │      regex on text      │
 │                         │                        │
 │                         │   6. BboxMapper         │
 │                         │      Tier 1: exact char │
 │                         │      Tier 2: word/line  │
 │                         │      Tier 3: null       │
 │                         │                        │
 │                         │   7. Rasterize pages    │
 │                         │      (max 3, max 1000px)│
 │                         │      Encode base64      │
 │                         │                        │
 │                         │ <─────────────────────  │
 │                         │   8. JSON response      │
 │                         │                        │
 │                    9. Render:                      │
 │                    - Page images                   │
 │                    - Bbox overlays (colored)       │
 │                    - Findings sidebar              │
 │                    - Risk badge                    │
 │ <───────────────────────│                        │
 │                         │                        │
 │  10. Clicks "Mask All"  │                        │
 │ ───────────────────────>│                        │
 │                    11. Local state flip            │
 │                    (overlays → solid black)        │
 │                    Risk badge → SAFE               │
 │ <───────────────────────│                        │
 │                         │                        │
 │  12. Clicks "Download"  │                        │
 │ ───────────────────────>│                        │
 │                    13. POST /redact               │
 │                    (file + finding_ids)            │
 │                         │───────────────────────> │
 │                         │                        │
 │                         │   14. Re-extract file   │
 │                         │   15. Look up stored    │
 │                         │       bboxes by ID      │
 │                         │   16. Rasterize pages   │
 │                         │   17. Draw black rects  │
 │                         │   18. Assemble PDF      │
 │                         │                        │
 │                         │ <─────────────────────  │
 │                         │   19. PDF blob          │
 │                         │                        │
 │                    20. Trigger download            │
 │                    21. Reset to upload state       │
 │                    22. Show "1 Doc Secured.        │
 │                         0 Bytes Retained."         │
 │ <───────────────────────│                        │
```

---

## 3. API Endpoints

### `GET /health`

**Purpose:** Check backend is alive; frontend uses this to decide mock mode.

```
Response (200):
{
  "status": "ok",
  "ocr_available": true,
  "version": "1.0.0"
}
```

---

### `POST /scan`

**Purpose:** Upload a document, detect PII, return page images + findings with bboxes.

```
Request: multipart/form-data
  - file: binary (PDF, PNG, or JPEG, max 10MB)

Response (200):
{
  "mode": "pdf_text" | "ocr_image",
  "page_count": 2,
  "pages_shown": 2,
  "pages": [
    {
      "index": 0,
      "image_b64": "iVBORw0KGgo...",
      "width": 1000,
      "height": 1294
    }
  ],
  "findings": [
    {
      "id": "f-001",
      "type": "AADHAAR",
      "value_masked": "XXXX XXXX 9012",
      "severity": "high",
      "confidence": 0.95,
      "page": 0,
      "bbox": {
        "x": 0.12,
        "y": 0.34,
        "w": 0.30,
        "h": 0.05
      },
      "bbox_level": "exact" | "word" | "line" | null
    }
  ],
  "risk_score": 85,
  "confidence_flag": "ok" | "low"
}
```

**Key changes from original spec:**

| Field | What Changed | Why |
|-------|-------------|-----|
| `mode` | NEW — indicates pdf_text or ocr_image | Debugging + UI messaging + demo explanation |
| `bbox` | Now **normalized 0.0–1.0** ratios | Frontend never calculates pixel offsets. Resize-proof. |
| `bbox_level` | NEW — "exact", "word", "line", or null | Frontend can style differently; judges see fallback working |
| `confidence` | NEW — 0.95 for regex, 0.70 for fuzzy | Makes it feel AI-powered without actual ML |
| `confidence_flag` | NEW — "ok" or "low" | Replaces hard OCR rejection. Always returns results. |
| `value_masked` | Partially masked display value | Frontend never handles raw PII display logic |
| `pages_shown` | NEW — how many of total pages rendered | Supports "Showing 3 of 8 pages" UI label |
| `session_id` | **REMOVED** | No in-memory store. File re-sent in /redact. |

**Error responses:**

```
400: { "error": "Unsupported file type. Upload PDF, PNG, or JPEG." }
400: { "error": "File too large. Maximum 10MB." }
422: { "error": "Could not extract text from document." }
```

---

### `POST /redact`

**Purpose:** Generate a redacted PDF with black rectangles over selected findings.

```
Request: multipart/form-data
  - file: binary (same file re-uploaded)
  - finding_ids: JSON string, e.g. '["f-001", "f-003"]'

Response (200): application/pdf (binary blob)

Response (400):
{ "error": "No findings to redact." }

Response (422):
{ "error": "Could not process file for redaction." }
```

**Key change:** Frontend sends `finding_ids`, NOT raw bbox coordinates. Backend re-runs detection on the file, matches findings by ID, and uses its own stored bboxes. This eliminates coordinate mismatch between frontend display and backend redaction.

**How finding ID matching works:**

```python
# Backend re-scans the file and rebuilds findings
# Matches by: type + value + page number (deterministic)
# finding_id = f"f-{hash(type + value + str(page))[:6]}"
# Same file + same engine = same IDs every time
```

---

## 4. Data Storage

### Answer: **NO database. NO in-memory session store.**

**What was removed and why:**

```
REMOVED: file_store dict + UUID sessions + TTL cleanup thread + threading.Lock

WHY:
- Session management was the #1 source of potential bugs
- Race condition between cleanup thread and /redact
- Missing session_id = broken download
- Extra state to debug under hackathon pressure
```

**What replaces it:**

| Data | Where It Lives | Lifetime |
|------|---------------|----------|
| Uploaded file | Frontend holds the File object in React state | Until page refresh |
| Page images | React state (base64 strings from /scan response) | Until page refresh |
| Findings list | React state (useReducer) | Until page refresh |
| Mask toggles | React state (Set of masked finding IDs) | Until page refresh |
| Original file for redaction | Re-sent by frontend in /redact POST | Single request |

**Mock data approach:**

```
/public/mock/
  ├── mock_response.json      ← Full /scan response with 2 pages, 5 findings
  ├── page_0.png              ← Sample Aadhaar letter image
  └── page_1.png              ← Sample PAN card image
```

`mock_response.json` structure:

```json
{
  "mode": "pdf_text",
  "page_count": 2,
  "pages_shown": 2,
  "pages": [
    { "index": 0, "image_b64": "...", "width": 1000, "height": 1294 },
    { "index": 1, "image_b64": "...", "width": 1000, "height": 800 }
  ],
  "findings": [
    {
      "id": "f-mock-001",
      "type": "AADHAAR",
      "value_masked": "XXXX XXXX 9012",
      "severity": "high",
      "confidence": 0.95,
      "page": 0,
      "bbox": { "x": 0.15, "y": 0.42, "w": 0.35, "h": 0.04 },
      "bbox_level": "exact"
    },
    {
      "id": "f-mock-002",
      "type": "PAN",
      "value_masked": "XXXXX1234X",
      "severity": "high",
      "confidence": 0.95,
      "page": 0,
      "bbox": { "x": 0.15, "y": 0.55, "w": 0.25, "h": 0.04 },
      "bbox_level": "exact"
    },
    {
      "id": "f-mock-003",
      "type": "PHONE",
      "value_masked": "XXXXXX7890",
      "severity": "medium",
      "confidence": 0.95,
      "page": 1,
      "bbox": { "x": 0.20, "y": 0.30, "w": 0.28, "h": 0.04 },
      "bbox_level": "word"
    },
    {
      "id": "f-mock-004",
      "type": "EMAIL",
      "value_masked": "r***@gmail.com",
      "severity": "medium",
      "confidence": 0.95,
      "page": 1,
      "bbox": { "x": 0.20, "y": 0.45, "w": 0.40, "h": 0.04 },
      "bbox_level": "exact"
    },
    {
      "id": "f-mock-005",
      "type": "AADHAAR",
      "value_masked": "XXXX XXXX 3456",
      "severity": "high",
      "confidence": 0.70,
      "page": 1,
      "bbox": null,
      "bbox_level": null
    }
  ],
  "risk_score": 100,
  "confidence_flag": "ok"
}
```

---

## 5. Mock Strategy

### Three layers of fallback, from automatic to manual:

```
Layer 1: AUTO MOCK (backend unreachable)
─────────────────────────────────────────
On mount: fetch('/health')
  If fails OR non-200 → set MOCK_MODE = true
  All API calls return mock_response.json
  Yellow banner: "Demo mode — backend unavailable"
  Download button: generates a blank PDF client-side

Layer 2: FORCE DEMO MODE (manual trigger)
─────────────────────────────────────────
Keyboard: Ctrl + Shift + D
  Loads: perfect sample PDF + precomputed results
  Bypasses upload entirely
  Shows full workflow with ideal data
  Use case: everything fails, you still demo

Layer 3: PARTIAL FAILURE (backend works, but OCR/PDF broken)
─────────────────────────────────────────────────────────────
/scan returns confidence_flag: "low"
  UI shows: "Low image clarity — results may be incomplete"
  Findings still displayed (never rejected)
  
/scan returns findings with bbox: null
  UI renders finding in sidebar only (no overlay)
  Sidebar shows: "Location unavailable" tag
  Everything else works normally
```

**Mock toggle implementation:**

```jsx
// App.jsx
const [mockMode, setMockMode] = useState(false);

useEffect(() => {
  fetch('/api/health')
    .then(r => { if (!r.ok) setMockMode(true); })
    .catch(() => setMockMode(true));
}, []);

useEffect(() => {
  const handler = (e) => {
    if (e.ctrlKey && e.shiftKey && e.key === 'D') {
      setMockMode(prev => !prev);
    }
  };
  window.addEventListener('keydown', handler);
  return () => window.removeEventListener('keydown', handler);
}, []);
```

---

## 6. Failure Handling Plan

| Failure | Detection | User Sees | Technical Action |
|---------|-----------|-----------|-----------------|
| Backend down | `/health` fails on mount | Yellow "Demo mode" banner, mock data loads | `MOCK_MODE = true`, all calls use mock JSON |
| `/scan` timeout (>5s) | `AbortController` + timer | After 3s: "Still processing… large document detected." After 8s: "Switching to demo mode." | Cancel request, load mock response |
| `/scan` 400 error | HTTP status | Toast: "Unsupported file. Try PDF, PNG, or JPEG." | No state change, user can retry |
| `/scan` 500 error | HTTP status | Toast: "Something went wrong. Retrying…" → auto-retry once → if fails: "Switching to demo mode" | One retry, then mock fallback |
| Empty findings | `findings.length === 0` | Green badge: "No sensitive data detected" + option to re-scan | Normal flow, just no overlays |
| OCR low confidence | `confidence_flag === "low"` | Orange banner: "Low image clarity — results may be incomplete" | Show all findings anyway, never reject |
| Bbox mapping fails | `bbox === null` on some findings | Finding shows in sidebar with "Location unavailable" tag. No overlay on page. | Graceful degradation per-finding |
| `/redact` fails | HTTP error | Toast: "Download failed. You can screenshot the masked view." | Offer client-side canvas-based fallback |
| Tesseract missing | `/health` returns `ocr_available: false` | Image uploads show: "OCR unavailable. Please upload a text-layer PDF." | PDF path still works. Only image path disabled. |
| File too large | Frontend validation | Toast: "File too large. Maximum 10MB." | Reject before upload |

**Timeout implementation:**

```jsx
async function scanFile(file, onSlow) {
  const controller = new AbortController();
  
  // Show "still processing" after 3 seconds
  const slowTimer = setTimeout(() => onSlow(), 3000);
  
  // Hard timeout at 8 seconds
  const hardTimer = setTimeout(() => controller.abort(), 8000);
  
  try {
    const form = new FormData();
    form.append('file', file);
    const res = await fetch('/api/scan', {
      method: 'POST',
      body: form,
      signal: controller.signal,
    });
    clearTimeout(slowTimer);
    clearTimeout(hardTimer);
    if (!res.ok) throw new Error(res.status);
    return await res.json();
  } catch (err) {
    clearTimeout(slowTimer);
    clearTimeout(hardTimer);
    return null; // caller switches to mock
  }
}
```

---

## 7. Backend Implementation Details (Fixes Applied)

### 7.1 PII Engine — Fixed Regex Patterns

```python
import re

PATTERNS = {
    "AADHAAR": {
        "pattern": r"[2-9]\d{3}[\s-]?\d{4}[\s-]?\d{4}",
        "severity": "high",
        # Requires all 12 digits. Won't partial-match "1234" alone.
        # The [2-9] prefix prevents false positives on random 12-digit numbers.
    },
    "PAN": {
        "pattern": r"[A-Z]{5}\d{4}[A-Z]",
        "severity": "high",
    },
    "PHONE": {
        "pattern": r"(?:\+91[\-\s]?)?[6-9]\d{9}",
        "severity": "medium",
    },
    "EMAIL": {
        "pattern": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
        "severity": "medium",
    },
}

def detect(text: str) -> list[dict]:
    findings = []
    seen = set()  # Deduplicate overlapping matches
    for pii_type, config in PATTERNS.items():
        for match in re.finditer(config["pattern"], text):
            key = (pii_type, match.group(), match.start())
            if key in seen:
                continue
            seen.add(key)
            findings.append({
                "type": pii_type,
                "value": match.group(),
                "start": match.start(),
                "end": match.end(),
                "severity": config["severity"],
                "confidence": 0.95,  # Regex match = high confidence
            })
    return findings
```

### 7.2 Bbox Mapper — 3-Tier Fallback (CRITICAL FIX)

```python
def map_bbox_pdf(finding, chars, page_width, page_height):
    """
    Tier 1: Exact character-level bbox
    Tier 2: Line-level bbox (safe fallback)
    Tier 3: None (sidebar only)
    """
    try:
        # --- BUILD STRING WITH SPACES (FIX FOR ISSUE #1) ---
        text_parts = []
        char_map = []  # index_in_string → char_object
        
        for i, char in enumerate(chars):
            # Detect word boundary by horizontal gap
            if i > 0 and char['x0'] - chars[i-1]['x1'] > chars[i-1].get('size', 10) * 0.3:
                text_parts.append(' ')
                char_map.append(None)  # space has no char object
            text_parts.append(char['text'])
            char_map.append(char)
        
        full_text = ''.join(text_parts)
        
        # Find the match in the reconstructed string
        match = re.search(re.escape(finding["value"]), full_text)
        if not match:
            # Try without spaces in search value
            collapsed = finding["value"].replace(" ", "").replace("-", "")
            match = re.search(re.escape(collapsed),
                              full_text.replace(" ", ""))
            if not match:
                raise ValueError("No match in char stream")
        
        # TIER 1: Exact character bboxes
        matched_chars = [
            char_map[i] for i in range(match.start(), match.end())
            if i < len(char_map) and char_map[i] is not None
        ]
        
        if matched_chars:
            bbox = {
                "x": min(c['x0'] for c in matched_chars) / page_width,
                "y": min(c['top'] for c in matched_chars) / page_height,
                "w": (max(c['x1'] for c in matched_chars) -
                      min(c['x0'] for c in matched_chars)) / page_width,
                "h": (max(c['bottom'] for c in matched_chars) -
                      min(c['top'] for c in matched_chars)) / page_height,
            }
            return bbox, "exact"
    
    except Exception:
        pass
    
    # TIER 2: Line-level fallback
    try:
        # Find any line containing part of the value
        lines = group_chars_into_lines(chars)  # group by y-coordinate
        for line_chars in lines:
            line_text = ''.join(c['text'] for c in line_chars)
            if finding["value"].replace(" ", "") in line_text.replace(" ", ""):
                bbox = {
                    "x": min(c['x0'] for c in line_chars) / page_width,
                    "y": min(c['top'] for c in line_chars) / page_height,
                    "w": (max(c['x1'] for c in line_chars) -
                          min(c['x0'] for c in line_chars)) / page_width,
                    "h": (max(c['bottom'] for c in line_chars) -
                          min(c['top'] for c in line_chars)) / page_height,
                }
                return bbox, "line"
    except Exception:
        pass
    
    # TIER 3: No bbox
    return None, None


def group_chars_into_lines(chars, tolerance=3):
    """Group characters into lines by y-coordinate proximity."""
    if not chars:
        return []
    lines = []
    current_line = [chars[0]]
    for char in chars[1:]:
        if abs(char['top'] - current_line[0]['top']) < tolerance:
            current_line.append(char)
        else:
            lines.append(current_line)
            current_line = [char]
    lines.append(current_line)
    return lines
```

### 7.3 OCR Bbox Mapper (for images)

```python
def map_bbox_ocr(finding, ocr_data, img_width, img_height):
    """
    Maps regex findings to OCR word bounding boxes.
    Returns normalized bbox (0.0–1.0).
    """
    try:
        # Build text from OCR words with position tracking
        words = []
        full_text_parts = []
        for i in range(len(ocr_data['text'])):
            word = ocr_data['text'][i].strip()
            if not word:
                continue
            start_idx = len(' '.join(full_text_parts) + (' ' if full_text_parts else ''))
            words.append({
                'text': word,
                'left': ocr_data['left'][i],
                'top': ocr_data['top'][i],
                'width': ocr_data['width'][i],
                'height': ocr_data['height'][i],
                'start': start_idx,
                'end': start_idx + len(word),
            })
            full_text_parts.append(word)
        
        full_text = ' '.join(full_text_parts)
        
        match = re.search(re.escape(finding["value"]), full_text)
        if not match:
            return None, None
        
        # Find all words that overlap with the match span
        covered = [
            w for w in words
            if w['start'] < match.end() and w['end'] > match.start()
        ]
        
        if not covered:
            return None, None
        
        bbox = {
            "x": min(w['left'] for w in covered) / img_width,
            "y": min(w['top'] for w in covered) / img_height,
            "w": (max(w['left'] + w['width'] for w in covered) -
                  min(w['left'] for w in covered)) / img_width,
            "h": (max(w['top'] + w['height'] for w in covered) -
                  min(w['top'] for w in covered)) / img_height,
        }
        return bbox, "word"
    
    except Exception:
        return None, None
```

### 7.4 Image Preprocessing — Fixed (No Denoising by Default)

```python
from PIL import Image, ImageOps

def preprocess(img: Image.Image, denoise: bool = False) -> Image.Image:
    """
    Fast preprocessing. Denoising DISABLED by default (saves 1-2 sec/page).
    Enable only if OCR results are garbage.
    """
    img = ImageOps.autocontrast(img)
    
    if denoise:
        import cv2
        import numpy as np
        arr = np.array(img.convert('L'))
        if np.std(arr) < 30:  # Only denoise if actually noisy
            arr = cv2.fastNlMeansDenoising(arr, h=5)
            img = Image.fromarray(arr)
    
    return img
```

### 7.5 Scanned PDF Detection (NEW FIX)

```python
import pdfplumber

def extract_text_and_mode(file_bytes: bytes):
    """
    Returns (text, chars_per_page, mode).
    Auto-detects scanned PDFs and falls back to OCR.
    """
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        all_text = ""
        all_chars = {}
        
        for i, page in enumerate(pdf.pages[:3]):  # Max 3 pages
            text = page.extract_text() or ""
            chars = page.chars
            all_text += text + "\n"
            all_chars[i] = chars
        
        if len(all_text.strip()) > 20:
            return all_text, all_chars, "pdf_text"
    
    # Scanned PDF: no extractable text → OCR fallback
    return None, None, "ocr_image"
```

### 7.6 Value Masking Utility

```python
def mask_value(pii_type: str, value: str) -> str:
    if pii_type == "AADHAAR":
        digits = re.sub(r'\D', '', value)
        return f"XXXX XXXX {digits[-4:]}"
    elif pii_type == "PAN":
        return f"XXXXX{value[5:9]}X"
    elif pii_type == "PHONE":
        return f"XXXXXX{value[-4:]}"
    elif pii_type == "EMAIL":
        local, domain = value.split('@')
        return f"{local[0]}***@{domain}"
    return "XXXX"
```

### 7.7 Finding ID Generation (Deterministic)

```python
import hashlib

def generate_finding_id(pii_type: str, value: str, page: int, start: int) -> str:
    raw = f"{pii_type}:{value}:{page}:{start}"
    h = hashlib.md5(raw.encode()).hexdigest()[:6]
    return f"f-{h}"
```

---

## 8. Frontend Component Specifications

### State Shape (useReducer)

```typescript
interface State {
  phase: 'upload' | 'scanning' | 'review' | 'downloading';
  file: File | null;
  scanResult: ScanResponse | null;
  maskedIds: Set<string>;
  mockMode: boolean;
  slowWarning: boolean;
  error: string | null;
}

type Action =
  | { type: 'START_SCAN'; file: File }
  | { type: 'SCAN_SUCCESS'; result: ScanResponse }
  | { type: 'SCAN_SLOW' }
  | { type: 'SCAN_ERROR'; error: string }
  | { type: 'TOGGLE_MASK'; findingId: string }
  | { type: 'MASK_ALL' }
  | { type: 'UNMASK_ALL' }
  | { type: 'START_DOWNLOAD' }
  | { type: 'DOWNLOAD_DONE' }
  | { type: 'RESET' }
  | { type: 'SET_MOCK'; enabled: boolean };
```

### Component Tree

```
App
├── MockBanner (yellow bar, shown when mockMode=true)
├── UploadZone (phase=upload)
│   └── Dropzone (react-dropzone)
├── ScanningOverlay (phase=scanning)
│   ├── Spinner
│   └── SlowWarning (after 3s)
├── ReviewScreen (phase=review)
│   ├── DocumentViewer
│   │   ├── PageImage (img from base64)
│   │   └── RedactionOverlay[] (positioned divs)
│   ├── FindingsPanel
│   │   ├── FindingCard[] (type icon, masked value, severity, toggle)
│   │   └── RiskBadge
│   └── ActionBar
│       ├── MaskAllButton
│       └── DownloadButton
└── CompletionScreen (after download)
    └── "1 Document Secured. 0 Bytes Retained."
```

### Bbox Overlay Rendering (normalized coords)

```jsx
function RedactionOverlay({ finding, isMasked, pageWidth, pageHeight }) {
  if (!finding.bbox) return null;  // Tier 3: no overlay
  
  const style = {
    position: 'absolute',
    left: `${finding.bbox.x * 100}%`,
    top: `${finding.bbox.y * 100}%`,
    width: `${finding.bbox.w * 100}%`,
    height: `${finding.bbox.h * 100}%`,
    backgroundColor: isMasked ? '#000' : 'transparent',
    border: isMasked ? 'none' : `2px solid ${finding.severity === 'high' ? '#ef4444' : '#f97316'}`,
    borderRadius: '2px',
    transition: 'background-color 0.2s ease',
    pointerEvents: 'none',
  };
  
  return <div style={style} />;
}
```

### Findings Grouped by Page (Performance Fix)

```jsx
const findingsByPage = useMemo(() => {
  const map = new Map();
  (scanResult?.findings || []).forEach(f => {
    if (!map.has(f.page)) map.set(f.page, []);
    map.get(f.page).push(f);
  });
  return map;
}, [scanResult?.findings]);
```

---

## 9. Final Execution Flow (Demo Script)

```
STEP  ACTION                          WHAT HAPPENS                         WHAT JUDGES SEE
─────────────────────────────────────────────────────────────────────────────────────────────
1     Open app                        /health check passes                 Clean upload screen
                                      (or mock mode activates)

2     Drop sample_aadhaar.pdf         Frontend validates type + size       File appears in dropzone
                                      POST /scan fires                     Spinner + "Scanning..."

3     (wait 1-3 sec)                  Backend: extract → detect → map      If >3s: "Still processing..."
                                      Response arrives

4     Review screen loads             Page images render                   Document with colored
                                      Bbox overlays appear                 highlight boxes around
                                      Findings panel populates             Aadhaar, PAN, phone, email
                                      Risk badge shows HIGH (red)

5     Scroll findings panel           Each finding: icon, masked value,    Professional sidebar
                                      severity badge, toggle switch

6     Click "Mask All"                Local state flip (instant)           All highlights turn solid
                                      Risk badge → SAFE (green)            black. Badge goes green.
                                                                           Feels instant + satisfying.

7     Click "Download Safe Copy"      POST /redact with file + IDs         Loading indicator
                                      Backend generates redacted PDF       PDF downloads
                                      Browser triggers download

8     Completion screen               State resets                         "1 Document Secured.
                                                                            0 Bytes Retained."
                                                                           Clean, privacy-first ending.
```

**If anything breaks during demo:**

```
Backend down?       → Mock mode auto-activates. Full UI works with precomputed data.
Slow response?      → "Still processing..." message. Then mock fallback at 8s.
OCR garbage?        → "Low clarity" warning. Partial results shown (never empty).
Bbox mapping fails? → Findings appear in sidebar. Some without overlays. Still functional.
Everything fails?   → Ctrl+Shift+D loads perfect demo. You still win.
```

---

## 10. Build Order (Updated, 6 Hours)

| Order | Task | Time | Notes |
|-------|------|------|-------|
| **0** | Pre-build (night before) | 45 min | Download 3 sample docs. Test pytesseract + pdfplumber. Write regex patterns. Create mock_response.json. |
| **1** | FastAPI `/scan` skeleton (returns mock) | 30 min | Hardcode mock response. Get API contract working. Frontend can start immediately. |
| **2** | React: UploadZone + DocumentViewer + FindingsPanel | 90 min | Wire to /scan. Render page images + overlay divs. Mock mode toggle. |
| **3** | PIIEngine + BboxMapper (3-tier) | 90 min | The hard part. Test with real pdfplumber + pytesseract output. |
| **4** | Wire real /scan (replace mock) | 30 min | Connect engine to endpoint. Test end-to-end. |
| **5** | Mask toggle + POST /redact + download | 60 min | Frontend state flip + backend black rectangle drawing. |
| **6** | Mock fallback + /health check + error handling | 20 min | Wire up all failure paths. Test Ctrl+Shift+D. |
| **7** | Polish: loading states, toasts, slow warning, risk badge | 30 min | Final UI touches. |

**Why this order works:** Steps 1+2 can happen in parallel (one person on backend mock, one on frontend). Real engine (step 3) is developed against test data, not the live API. Integration (step 4) is a 30-minute swap.

---

## 11. Pre-Hackathon Checklist

- [ ] Install: `pip install pdfplumber PyMuPDF pytesseract Pillow opencv-python-headless fastapi uvicorn python-multipart`
- [ ] Install: `apt-get install tesseract-ocr` (Linux) or `brew install tesseract` (Mac)
- [ ] Verify: `python -c "import pytesseract; print(pytesseract.get_tesseract_version())"`
- [ ] Download 3 sample docs (Aadhaar letter PDF, PAN card photo, passport scan)
- [ ] Test: `pytesseract.image_to_string(Image.open("pan_card.jpg"))` → verify readable
- [ ] Test: `pdfplumber.open("aadhaar.pdf").pages[0].chars` → verify char objects exist
- [ ] Write all 4 regex patterns to `test_patterns.py`, test against 10 hand-crafted strings
- [ ] Create `mock_response.json` with hardcoded bbox coordinates from your sample
- [ ] Set up Vite project: `npm create vite@latest frontend -- --template react`
- [ ] Install frontend deps: `npm install react-dropzone tailwindcss @tailwindcss/vite`
- [ ] Configure Vite proxy: `/api` → `http://localhost:8000`

---

## 12. What Was Deliberately Excluded

| Feature | Why Excluded |
|---------|-------------|
| DOCX support | Separate extraction pipeline. Marginal demo value. |
| Cloud deploy | Localhost is faster, reliable, supports privacy narrative. |
| ML/LLM | Adds latency + failure modes for structurally rigid patterns. |
| Database | In-memory is sufficient. No persistence needed. |
| Auth | No users. Localhost. No threat model. |
| Animated risk gauge | Polish, not substance. Risk badge is sufficient. |
| Draggable bbox adjustment | High cost, edge case. Line-level fallback is simpler. |
| Session store | **Removed.** Was the #1 bug risk. File re-sent instead. |
| cv2 denoising (default) | **Disabled.** Saves 1-2s/page. Use clean test docs. |
| OCR rejection threshold | **Removed.** Always show results with confidence warning. |
