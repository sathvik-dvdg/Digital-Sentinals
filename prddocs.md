1. Problem Understanding
Organizations and individuals across India routinely handle documents containing highly sensitive personally identifiable information (PII) such as Aadhaar numbers, PAN card details, passport numbers, mobile numbers, and email addresses. When these documents are shared, stored, or processed without proper redaction, they create significant exposure to identity theft, financial fraud, and regulatory non-compliance.
1.1 Core Pain Points
•	No fast, offline-first tool exists for detecting and redacting India-specific PII patterns from uploaded documents.
•	Existing enterprise solutions (Presidio, Google DLP) are tuned for Western identifiers (SSN, NINO) and require heavy infrastructure, API keys, and cloud dependencies.
•	Manual redaction is error-prone, slow, and scales poorly — a single missed Aadhaar number in a shared PDF can lead to identity fraud.
•	Users distrust cloud-based redaction tools because uploading sensitive documents to a third-party server defeats the purpose of privacy protection.
1.2 Why This Matters
Business perspective: India’s Digital Personal Data Protection Act (DPDPA) 2023 imposes strict obligations on data fiduciaries. A lightweight redaction tool reduces compliance burden for small businesses, legal firms, and HR departments that lack dedicated privacy teams.
Technical perspective: Indian PII identifiers (Aadhaar: 12-digit with Verhoeff checksum, PAN: 5-alpha-4-digit-1-alpha) are structurally rigid and perfectly suited to deterministic regex detection. This eliminates the need for probabilistic ML models, reducing latency and build complexity to a level achievable within a hackathon timeframe.
2. Project Overview
Project Name: PII Shield
Objective: Build a single-session, zero-data-retention web application that accepts a PDF or image upload, automatically detects India-specific PII using regex pattern matching, presents findings in a visual review interface, and exports a securely redacted copy — all within a local-first architecture.
2.1 Key Goals
•	Detect five core Indian PII types (Aadhaar, PAN, mobile, email, passport) with ≥95% precision on clean documents.
•	Process a single-page document end-to-end (upload → scan → review → export) in under 8 seconds.
•	Produce a securely redacted PDF where masked content is irrecoverable (no hidden text layers beneath black bars).
•	Achieve zero data retention: no file touches disk, no database, no persistent storage.
2.2 Non-Goals
•	Multi-file or batch upload processing.
•	DOCX, spreadsheet, or other non-PDF/image format support.
•	Cloud deployment or multi-user authentication.
•	ML/NLP-based entity recognition (no spaCy, no Presidio, no LLM API calls).
•	Named entity recognition for unstructured PII such as names or addresses (regex-only scope).
•	Support for documents exceeding 5 pages or 10 MB.
3. User Analysis
3.1 Target Users
Persona	Description	Primary Need
Hackathon Judge	Technical evaluator assessing demo quality, innovation, and completeness	Visually compelling demo with clear before/after redaction flow
Compliance Officer	Privacy or legal team member at an Indian SMB or startup	Quick scan of documents before external sharing to catch exposed PII
HR Professional	Handles employee documents (Aadhaar, PAN copies) for onboarding	Redact sensitive fields before archiving or forwarding to payroll vendors
Freelance Developer	Solo developer handling client documents with embedded PII	Ad-hoc redaction without installing enterprise software or sharing files with a cloud service

3.2 User Journey
The primary interaction flow is a five-step linear sequence with no branching or authentication:
•	Step 1 — Upload: User opens the application in a browser, drags a PDF or image file onto the upload zone, or clicks to select a file.
•	Step 2 — Scan: System extracts text (pdfplumber for PDFs, pytesseract for images), runs regex detection, and returns page images with bounding box coordinates for each finding.
•	Step 3 — Review: User sees the document rendered with color-coded overlay boxes (red for high-severity items like Aadhaar/PAN, orange for medium-severity like email/phone). A sidebar lists each finding with type, partially masked value, and severity tag.
•	Step 4 — Mask: User clicks “Mask All” (or toggles individual findings in the nice-to-have version). Overlay boxes change from translucent color to solid black. Risk score gauge animates upward.
•	Step 5 — Export: User clicks “Download Safe Copy.” Backend rasterizes pages, draws opaque black rectangles over masked regions, and returns a flattened PDF. Browser triggers download.
4. Feature Requirements
4.1 Core Features (MVP)
F1: File Upload
Description: Drag-and-drop or click-to-select upload zone accepting a single PDF, PNG, or JPEG file.
Inputs: One file, max 10 MB, max 5 pages (for PDFs).
Processing: Frontend validates file type via MIME check and size. Sends multipart/form-data POST to /scan endpoint.
Outputs: Upload confirmation with processing spinner. Error toast for invalid files.
Edge Cases: Corrupt PDFs, password-protected PDFs (reject with message), zero-byte files, files with misleading extensions.
F2: Text Extraction
Description: Extract machine-readable text and word-level bounding box coordinates from the uploaded document.
Inputs: Raw file bytes from upload.
Processing: File type detection via magic bytes. PDF path: PyMuPDF rasterizes pages to PNG for display, pdfplumber extracts text with character-level positions. Image path: pytesseract image_to_data() returns word-level bounding boxes and recognized text.
Outputs: Structured text content with positional metadata per word/character.
Edge Cases: Scanned PDFs (images embedded in PDF containers — must route through OCR path). Rotated pages. Multi-column layouts. Handwritten content (will produce poor OCR; acceptable degradation).
F3: PII Detection Engine
Description: Run deterministic regex patterns against extracted text to identify India-specific PII.
Inputs: Extracted text string with positional metadata.
Processing: Five regex patterns executed sequentially: Aadhaar ([2-9]\d{3}\s?\d{4}\s?\d{4}), PAN ([A-Z]{5}\d{4}[A-Z]), Indian mobile ((?:\+91[\-\s]?)?[6-9]\d{9}), email (standard RFC pattern), passport ([A-Z]\d{7}). Each match is mapped back to bounding box coordinates. Severity assigned: high (Aadhaar, PAN, passport), medium (mobile, email).
Outputs: Array of findings: { id, type, value, bbox [x, y, w, h], page, severity }.
Edge Cases: Aadhaar numbers split across line breaks. Phone numbers with parentheses or dots as separators. PAN embedded in longer alphanumeric strings (false positives). Email addresses with unusual TLDs.
F4: Visual Document Viewer with Highlights
Description: Render page images with color-coded translucent overlay boxes positioned at each detected PII location.
Inputs: Page images (base64 PNG) and findings array from backend.
Processing: Frontend renders page images in a scrollable viewer. For each finding, an absolutely-positioned div is placed at the bbox coordinates with colored border and translucent fill (red for high severity, orange for medium).
Outputs: Interactive document view with highlighted PII regions. Sidebar panel listing all findings with type, partially masked value, and severity badge.
Edge Cases: Findings that overlap or are adjacent. Very small bounding boxes for short values. Pages with no findings (show clean with no overlays).
F5: Mask and Redact
Description: Allow user to mark all findings for redaction, visually replacing highlights with solid black bars.
Inputs: User click on “Mask All” button.
Processing: Frontend updates state: all findings marked as masked. Overlay divs transition from translucent color to solid black via CSS transition.
Outputs: Visual confirmation that all PII regions are covered with opaque black bars.
Edge Cases: User wants to unmask after masking (toggle behavior). Documents with zero findings (disable mask button, show success state).
F6: Redacted PDF Export
Description: Generate a downloadable PDF where masked PII regions are permanently and irrecoverably covered.
Inputs: Original file and list of bounding boxes to redact (sent via POST /redact).
Processing: Backend rasterizes each page to a bitmap image via PyMuPDF. Draws opaque black rectangles over specified bounding box coordinates using Pillow. Assembles pages into a new PDF via PyMuPDF. Returns PDF blob.
Outputs: Browser-triggered download of the redacted PDF file.
Edge Cases: Coordinate scaling mismatch between display resolution and export resolution. Very large documents producing large PDF blobs (mitigate with DPI cap at 150).
4.2 Secondary Features (Nice-to-Have)
F7: Risk Score Gauge
Description: Animated 0–100 gauge reflecting document risk level. Starts high when PII is detected, drops toward zero as items are masked.
Inputs: Findings count and severity weights.
Processing: Score = 100 − (masked_count / total_count × 100), weighted by severity. CSS transition animates the gauge arc and numeric display.
Outputs: Animated circular or semicircular gauge with numeric score and color gradient (red → green).
Edge Cases: Zero findings (show 100/100 safe). All masked (animate to 0 risk / full safe).
F8: Per-Item Mask Toggle
Description: Individual toggle switches on each finding in the sidebar, allowing selective masking.
Inputs: User toggle interaction on a specific finding.
Processing: State update for single finding’s masked boolean. Corresponding overlay div transitions independently.
Outputs: Individual finding switches between highlighted and blacked-out states.
Edge Cases: Rapid toggling causing render thrash (debounce state updates).
F9: Contextual Tooltips
Description: Hover tooltip on each highlighted region explaining why it was flagged.
Inputs: Mouse hover on a finding overlay.
Processing: Tooltip rendered with finding type and pattern description (e.g., “Matches Indian Aadhaar 12-digit format”).
Outputs: Tooltip overlay positioned near the finding without obscuring the document.
Edge Cases: Tooltip clipping at page edges. Mobile touch events (tap instead of hover).
5. Functional Requirements
5.1 System Behaviors
•	The system shall accept exactly one file per session. Uploading a new file replaces the previous scan.
•	The system shall detect file type using magic bytes, not file extension, to prevent spoofing.
•	The system shall reject files exceeding 10 MB with a user-facing error message.
•	The system shall reject PDFs exceeding 5 pages with a warning and offer to process the first 5 pages only.
•	The system shall complete the scan phase (extraction + detection) within 8 seconds for a single-page document.
•	The system shall not persist any uploaded file to disk. All processing occurs in memory; files are discarded after the HTTP response is sent.
•	The system shall return all findings with pixel-accurate bounding box coordinates relative to the rasterized page image dimensions.
5.2 Data Flow
Frontend sends multipart/form-data POST to /scan. Backend detects file type, extracts text with positional data, runs regex engine, rasterizes pages to base64 PNG images, and returns a JSON payload containing page images, findings array, and computed risk score. Frontend renders the viewer and sidebar. On export, frontend sends POST to /redact with the original file and bounding box list. Backend rasterizes, draws black rectangles, assembles PDF, and streams the blob back. Frontend triggers browser download.
5.3 Validation Rules
Field	Rule	Error Response
File type	Must be PDF, PNG, or JPEG (validated by magic bytes)	400: Unsupported file type. Please upload a PDF, PNG, or JPEG.
File size	Must be ≤10 MB	400: File exceeds 10 MB limit.
Page count	PDF must be ≤5 pages	400: Document exceeds 5-page limit. First 5 pages will be processed.
Aadhaar pattern	Must not start with 0 or 1 (invalid Aadhaar)	Finding excluded from results.
PAN format	Must match [A-Z]{5}[0-9]{4}[A-Z] exactly	Finding excluded if embedded in longer alphanumeric string.

6. Non-Functional Requirements
Category	Requirement	Target
Performance	Single-page scan latency (upload to results rendered)	<8 seconds
Performance	Redacted PDF generation time	<5 seconds per page
Performance	Frontend render of page image with 20 overlay boxes	<500ms
Scalability	Concurrent users supported	Single user (localhost). No horizontal scaling required.
Security	File persistence	Zero. In-memory only. No disk writes, no temp files, no database.
Security	Redaction integrity	No selectable text beneath black bars. Rasterize-and-overlay approach eliminates hidden text layers.
Security	Network exposure	Localhost only. No external API calls, no telemetry, no analytics.
Reliability	OCR accuracy on clean printed documents	≥90% character-level accuracy (pytesseract default with English model).
Reliability	Regex precision on clean text	≥95% (minimal false positives on structured Indian PII patterns).
Availability	Uptime target	N/A (single-session local application, not a hosted service).

7. System Architecture
7.1 High-Level Architecture
The system follows a hybrid client-heavy architecture with a thin Python backend. The frontend handles all UI rendering, state management, and user interaction. The backend handles file processing (OCR, text extraction, PDF rasterization) and redacted PDF generation. Communication occurs over two REST endpoints on localhost.
7.2 Frontend (React + Vite + Tailwind CSS)
Component	Responsibility
UploadZone	Drag-and-drop file input. Validates type and size. Posts multipart/form-data to backend.
DocumentViewer	Renders base64 page images. Overlays absolutely-positioned colored divs at finding bounding box coordinates.
FindingsPanel	Sidebar listing each detected entity: type, partially masked value, severity badge, and per-item toggle (nice-to-have).
RiskBadge	Animated semicircular gauge (0–100) showing risk score. CSS transitions for color and arc animation.
ActionBar	Contains “Mask All” and “Download Safe Copy” buttons. Disabled states when no findings or no masks applied.

State management: useState + useReducer for findings list and mask states. No external state library.
7.3 Backend (FastAPI, Python)
Endpoint	Responsibility
POST /scan	Receives file, detects type via magic bytes, extracts text (pdfplumber for PDFs, pytesseract for images), runs regex engine, rasterizes pages to PNG, returns JSON with page images and findings.
POST /redact	Receives original file + bounding box list. Rasterizes pages via PyMuPDF, draws black rectangles via Pillow, assembles flattened PDF, returns PDF blob.
GET /health	Returns 200 OK. Used for demo startup verification.

7.4 Data Flow
•	1. User drops file → Frontend validates → POST /scan with multipart/form-data.
•	2. Backend detects file type → Routes to PDF or image extraction pipeline.
•	3. PDF path: PyMuPDF rasterizes pages, pdfplumber extracts text with character positions.
•	4. Image path: pytesseract image_to_data() returns word-level bounding boxes + text.
•	5. Regex engine runs on extracted text → Matches mapped to bounding box coordinates.
•	6. Backend returns JSON: { pages: [{ image_b64, width, height }], findings: [...], risk_score }.
•	7. Frontend renders page images with overlay boxes → User reviews and masks.
•	8. User clicks Download → POST /redact with file + bbox list → Backend returns PDF blob → Browser download.
8. Tech Stack Justification
Layer	Choice	Justification
Frontend Framework	React + Vite	Vite provides instant HMR and sub-second dev server startup. React’s component model maps cleanly to the viewer/sidebar/gauge UI structure. CRA is deprecated and adds unnecessary build overhead.
Styling	Tailwind CSS	Utility-first classes eliminate CSS file management and naming decisions. Faster iteration under hackathon time pressure than writing custom stylesheets.
Animation	CSS Transitions	Native CSS handles opacity, color, and width transitions for the gauge and mask toggle. Framer Motion adds a dependency and learning curve with no MVP benefit.
Backend	FastAPI (Python)	Async request handling, built-in request validation, auto-generated API docs for development. Native access to the Python ecosystem for PDF and OCR processing.
PDF Reading	PyMuPDF (fitz)	Fastest Python PDF library for page rasterization. Combined with pdfplumber for text extraction with character-level positions (PyMuPDF’s text position mapping is less reliable).
OCR	pytesseract	Proven, local, no API key. Sub-3 second OCR per page vs. 10–30s for in-browser Tesseract.js. EasyOCR is heavier to install; Google Vision API adds network dependency.
PII Detection	Native Python regex	Deterministic, zero-latency, zero-dependency. Indian PII patterns are structurally rigid (Aadhaar = 4-4-4 digits, PAN = 5α+4d+1α). Presidio/LLM APIs are over-engineering.
PDF Output	PyMuPDF + Pillow	Rasterize pages to bitmaps, draw opaque rectangles with Pillow, reassemble into PDF with PyMuPDF. One-library pipeline for read and write.
Image Preprocessing	OpenCV (optional)	Grayscale conversion and thresholding improve OCR accuracy on poor-quality scans. Budget max 30 minutes on this; not critical for clean demo documents.

9. API Design
9.1 POST /scan
Purpose: Upload a document, extract text, detect PII, and return page images with findings.
Content-Type: multipart/form-data
Request
Field	Type	Required	Description
file	File (binary)	Yes	PDF, PNG, or JPEG. Max 10 MB.

Response (200 OK)
Field	Type	Description
pages	Array<Page>	Each page contains: image_b64 (string), width (int), height (int).
findings	Array<Finding>	Each finding contains: id (string), type (enum), value (string, partially masked), bbox (object: x, y, w, h), page (int), severity (enum: high | medium | low).
risk_score	Integer (0–100)	Computed risk score based on finding count and severity weights.

Error Responses
Status	Condition
400	Unsupported file type, file too large, or PDF exceeds page limit.
422	File is corrupt or unreadable.
500	Unexpected server error during processing.

9.2 POST /redact
Purpose: Generate a redacted PDF with specified bounding boxes permanently blacked out.
Content-Type: multipart/form-data
Request
Field	Type	Required	Description
file	File (binary)	Yes	Original file (same as uploaded to /scan).
redactions	JSON string	Yes	Array of objects: { page (int), bbox: { x, y, w, h } }.

Response (200 OK)
Content-Type: application/pdf
Binary PDF blob. Frontend triggers download via Blob URL and anchor click.

9.3 GET /health
Purpose: Startup verification.
Response: 200 OK with body: { "status": "healthy" }.
10. Database Design
Not applicable. This system deliberately uses no database, no file system persistence, and no caching layer. All document processing occurs in-memory within the scope of a single HTTP request. Files are discarded after the response is sent. This is a core architectural decision that reinforces the zero-data-retention privacy guarantee.
Session state (findings list, mask toggles, risk score) is held entirely in frontend React state and is lost on page refresh. This is acceptable for the single-session use case.
11. Success Metrics
KPI	Target	Measurement Method
Scan accuracy (precision)	≥95% on clean printed documents	Test against a curated set of 10 sample documents with known PII locations. Count false positives and false negatives.
End-to-end latency	<8 seconds for single-page scan	Time from upload click to results rendered, measured via browser DevTools network panel.
Redaction integrity	0 recoverable text under black bars	Open exported PDF in a text editor and search for original PII values. Attempt text selection over redacted regions.
Demo completion rate	Full flow in <90 seconds live	Timed dry run: upload → scan → review → mask → download within 90 seconds.
Judge “wow factor”	Risk gauge animation noticed and commented on	Qualitative: at least one judge mentions the visual risk indicator during Q&A.

12. Risks and Limitations
12.1 Technical Risks
Risk	Severity	Mitigation
OCR accuracy on low-quality images (rotated, handwritten, poor scans)	High	Use clean, controlled sample documents for demo. Add optional OpenCV preprocessing (grayscale, thresholding) but cap effort at 30 minutes.
Bounding box misalignment between regex matches and pixel coordinates	High	For pytesseract: merge adjacent word boxes when a match spans multiple words (e.g., spaced Aadhaar). For pdfplumber: use character-level positions. Test alignment early with known coordinates.
Large PDFs slow to rasterize and transmit as base64	Medium	Cap at 5 pages. Rasterize at 150 DPI (not 300). Show progress indicator during processing.
Regex false positives on numeric sequences that resemble Aadhaar or PAN	Medium	Add boundary checks: Aadhaar must not be preceded/followed by additional digits. PAN must be word-bounded. Accept that some false positives are tolerable for a hackathon demo.
pytesseract installation issues on demo machine	Low	Pre-install and verify during setup. Include a requirements.txt with pinned versions. Test the /health endpoint before demo.

12.2 Product Risks
•	Scope creep: Adding DOCX support, batch upload, or cloud deployment will consume time without adding demo impact. The non-goals list exists to prevent this.
•	Over-polishing UI at the expense of core detection accuracy: A beautiful interface that misses Aadhaar numbers is a failed product. Build order prioritizes the regex engine first.
•	Demo environment failure: Network issues, missing dependencies, or port conflicts can kill a live demo. Mitigation: run everything on localhost, pre-install all packages, and rehearse the full flow at least twice.
12.3 Assumptions
•	The demo machine has Python 3.9+, Node.js 18+, and Tesseract OCR pre-installed.
•	Sample documents will be clean, printed, English-language documents with standard fonts.
•	The target audience (hackathon judges) values a complete, polished end-to-end flow over breadth of features.
•	Regex-based detection is sufficient for structurally rigid Indian PII patterns. Unstructured PII (names, addresses) is explicitly out of scope.
•	Single-user, single-session usage eliminates the need for authentication, authorization, or session management.

