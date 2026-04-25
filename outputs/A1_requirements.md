## Features

### Must Have
- `Single-file upload for PDF, PNG, and JPEG`: The UI accepts exactly one file up to 10 MB, rejects unsupported files, and replaces the previous session file when a new one is selected.
- `Backend health check with automatic mock fallback`: On app load, the frontend calls `GET /health` and enables mock mode if the request fails or returns a non-200 response.
- `Regex-based PII scan`: `POST /scan` detects Aadhaar, PAN, phone, and email using the canonical regex patterns and returns findings that match the `ScanResponse` schema in `agents.md` Section 3.2.
- `Page preview rendering`: The scan response includes up to 3 rasterized page previews with base64 PNG payloads and rendered dimensions, and the frontend displays them in the review screen.
- `Normalized overlay rendering`: Findings with a non-null `bbox` are rendered as overlays using normalized `0.0-1.0` coordinates converted to percentages in the frontend.
- `Findings review panel`: The UI lists every finding with masked display value, severity, page reference, and an individual mask toggle.
- `Mask all and unmask all state handling`: The reducer supports toggling individual findings plus full-session mask and unmask actions without mutating the scan result payload.
- `Risk score display`: The UI shows a risk badge whose visible state reflects the counts of currently unmasked findings using the Section 7 `V4` logic.
- `Redacted PDF export`: `POST /redact` accepts the original file and a JSON array of finding UUIDs, uses backend-side bbox lookup, and returns a downloadable PDF blob with opaque redactions.
- `Slow scan warning`: If a real `/scan` request takes longer than 3 seconds, the frontend dispatches `SCAN_SLOW` and displays a warning while the request is still in progress.
- `Keyboard-forced mock mode`: Pressing `Ctrl+Shift+D` enables mock mode immediately and drives a complete demo flow without backend calls.
- `Zero data retention`: The backend performs all processing in memory, does not write uploaded files or extracted text to disk, and stores only bbox data in the in-memory cache.

### Should Have
- `Graceful scanned-document handling`: Text PDFs use direct extraction first, while image files and scanned PDFs fall back to OCR when text extraction is insufficient.
- `Three-tier bbox fallback`: Tier 1 exact char mapping, Tier 2 word or line mapping, and Tier 3 sidebar-only findings with `bbox: null`.
- `Autocontrast preprocessing`: OCR preprocessing uses autocontrast only to improve readability without adding latency-heavy denoising.
- `Clear failure messaging`: The UI surfaces contract-defined scan and redact errors without breaking the session flow.
- `Completion state`: After a successful download, the app transitions to a completion screen and allows reset to the upload phase.

### Won't Have (MVP)
- `Database or persistent session storage`: Excluded by architecture; the backend must remain stateless outside an ephemeral in-memory bbox cache.
- `Authentication or multi-user features`: Excluded because the MVP runs on localhost only.
- `DOCX or spreadsheet support`: Excluded by the product and architecture constraints.
- `ML, NER, or LLM-based detection`: Excluded because regex is the mandated detection path.
- `Cloud deployment or external API calls`: Excluded because privacy-first localhost processing is a core requirement.
- `Server-side file retention`: Excluded because uploaded content must not persist after request handling.
- `Additional endpoints beyond /health, /scan, and /redact`: Excluded because Section 3.2 defines the immutable API surface.

## User Flows

### Primary Scan And Redact Flow
1. User opens the app and the frontend calls `GET /health`.
2. If `GET /health` succeeds, the app stays in live mode; otherwise it enables mock mode automatically.
3. User uploads a single PDF, PNG, or JPEG file.
4. Frontend validates the file client-side and dispatches `START_SCAN`.
5. Frontend sends `POST /scan` with multipart form data unless mock mode is enabled.
6. Backend extracts text, runs regex detection, maps bboxes, rasterizes up to 3 pages, and returns the contract-shaped scan response.
7. Frontend dispatches `SCAN_SUCCESS`, renders the page previews, shows overlays for findings with bboxes, and lists all findings in the sidebar.
8. User toggles individual findings or clicks mask-all controls to decide what should be redacted.
9. Frontend recomputes the displayed risk state from the currently unmasked findings.
10. User clicks download and the frontend dispatches `START_DOWNLOAD`.
11. Frontend sends `POST /redact` with the original file and a JSON string of masked finding UUIDs unless mock mode is enabled.
12. Backend reconstructs redaction coordinates from its in-memory cache, generates a PDF, and returns the blob.
13. Frontend triggers a download, dispatches `DOWNLOAD_DONE`, and shows the completion screen.

### Backend Unavailable Demo Flow
1. User opens the app while the backend is unavailable.
2. The `GET /health` request fails or returns non-200.
3. Frontend dispatches `SET_MOCK` with `enabled: true`.
4. User uploads a file and the app skips real `/scan` calls.
5. Frontend loads `frontend/src/mock/mock_response.json` into state and renders the full review experience.
6. User masks findings and downloads a locally generated demo PDF without calling `/redact`.

### Forced Mock Flow
1. User presses `Ctrl+Shift+D`.
2. Frontend enables mock mode immediately.
3. The rest of the upload, review, mask, and completion flow runs entirely from local mock data.

## Constraints Confirmed

- The immutable API contract in `agents.md` Section 3.2 is the source of truth for all backend and frontend integration.
- The immutable frontend state and component prop contracts in Sections 3.3 and 3.4 must be implemented exactly.
- Only Aadhaar, PAN, phone, and email are in scope for the MVP regex engine.
- Rasterized previews are capped at 3 pages and bbox values are normalized ratios, not raw pixels.
- Uploaded files are re-sent to `/redact`; there is no backend session state beyond ephemeral bbox cache entries.
- Mock mode must activate automatically when `/health` fails and must not fire real `/scan` or `/redact` requests.
