## Component Diagram (text)

### Frontend
- `App.jsx`: Root orchestrator for health check, reducer state, keyboard shortcut, scan/download handlers, and phase-based screen rendering.
- `MockBanner.jsx`: Displays when `mockMode` is enabled.
- `UploadZone.jsx`: Receives a single file and forwards it through `onFile(file)`.
- `ScanningOverlay.jsx`: Shows scan progress and the slow warning when `slowWarning` is true.
- `DocumentViewer.jsx`: Renders the `pages` array and overlays `RedactionOverlay` for findings on each page.
- `RedactionOverlay.jsx`: Converts normalized bbox values to CSS percentages and renders either highlight or black mask styles.
- `FindingsPanel.jsx`: Receives findings, current mask state, toggle handler, and risk score display data.
- `FindingCard.jsx`: Shows one finding with masked display value, severity, page metadata, and a toggle.
- `RiskBadge.jsx`: Displays the current risk state passed from the parent.
- `ActionBar.jsx`: Triggers mask-all and download actions and reflects download state.
- `CompletionScreen.jsx`: Final success state with reset action.

### Backend
- `main.py`: Single FastAPI application containing the health endpoint, scan endpoint, redact endpoint, regex engine, extraction helpers, bbox mapping helpers, rasterization helpers, and response builders.

## Data Flow (annotated with payload types)

### Health Check
1. `App.jsx` mount -> `GET /api/health`
2. Response payload type:

```ts
{
  status: "ok";
  ocr_available: boolean;
  version: "1.0.0";
}
```

3. If the request fails or returns non-200, `App.jsx` dispatches `SET_MOCK` with `{ enabled: true }`.

### Scan Flow
1. `UploadZone.jsx` emits `File`.
2. `App.jsx` dispatches:

```ts
{ type: "START_SCAN"; file: File }
```

3. Live mode request:

```ts
POST /api/scan
Content-Type: multipart/form-data
Body: { file: File }
```

4. Backend response payload type:

```ts
interface ScanResponse {
  mode: "pdf_text" | "ocr_image";
  page_count: number;
  pages: Array<{
    page_number: number;
    image_b64: string;
    width: number;
    height: number;
  }>;
  findings: Array<{
    id: string;
    type: "aadhaar" | "pan" | "phone" | "email";
    value: string;
    raw_value: string;
    page: number;
    severity: "high" | "medium";
    confidence: number;
    bbox:
      | {
          x: number;
          y: number;
          w: number;
          h: number;
        }
      | null;
  }>;
  risk_score: {
    level: "HIGH" | "MEDIUM" | "SAFE";
    total_findings: number;
    high_count: number;
    medium_count: number;
  };
}
```

5. Frontend reducer dispatch:

```ts
{ type: "SCAN_SUCCESS"; result: ScanResponse }
```

6. `DocumentViewer.jsx` consumes:
- `pages: ScanResponse["pages"]`
- `findings: ScanResponse["findings"]`
- `maskedIds: Set<string>`

7. `FindingsPanel.jsx` consumes:
- `findings: ScanResponse["findings"]`
- `maskedIds: Set<string>`
- `riskScore: ScanResponse["risk_score"]` or a derived object with the same shape

### Redact Flow
1. `ActionBar.jsx` invokes download handler.
2. `App.jsx` computes selected redaction IDs from `maskedIds` and dispatches:

```ts
{ type: "START_DOWNLOAD" }
```

3. Live mode request:

```ts
POST /api/redact
Content-Type: multipart/form-data
Body: {
  file: File,
  finding_ids: string // JSON array of UUID strings
}
```

4. Backend response type:
- `Content-Type: application/pdf`
- body: PDF binary blob

5. Frontend triggers a browser download and dispatches:

```ts
{ type: "DOWNLOAD_DONE" }
```

## Error States

- `unsupported_file_type`: Backend returns `400`; frontend shows a user-facing upload error and stays in the upload phase.
- `file_too_large`: Backend returns `400`; frontend shows an error and stays in the upload phase.
- `no_text_extracted`: Backend returns `400`; frontend shows an error and stays in the upload phase.
- `processing_failed`: Backend returns `500`; frontend dispatches `SCAN_ERROR` and may switch to mock mode if live scanning is unavailable.
- `invalid_finding_ids`: Backend returns `400`; frontend re-enables download UI and shows an error.
- `file_mismatch`: Backend returns `400`; frontend re-enables download UI and shows an error.
- `redaction_failed`: Backend returns `500`; frontend re-enables download UI and shows an error.
- `scan timeout`: Frontend aborts the live request after 8 seconds, dispatches `SCAN_ERROR`, enables mock mode, and loads mock data.
- `bbox: null`: Frontend still lists the finding in `FindingsPanel` but renders no overlay in `DocumentViewer`.

## Mock Mode Conditions

- Enable mock mode if the initial `/health` request fails for any reason.
- Enable mock mode if the initial `/health` request returns a non-200 response.
- Enable mock mode when the user presses `Ctrl+Shift+D`.
- Enable mock mode after a live `/scan` timeout or unrecoverable fetch failure.
- While `mockMode` is true, the frontend must not issue real `/scan` or `/redact` requests.
- In mock mode, `SCAN_SLOW` must not be dispatched.
- In mock mode, the frontend loads `frontend/src/mock/mock_response.json` and uses a locally generated PDF blob for the download flow.

## BboxMapper Fallback Logic

- `Tier 1: exact character match`
  For text PDFs, the backend reconstructs searchable text from character-level extraction data and maps a finding to the smallest union of matching characters. This produces the most precise bbox.
- `Tier 2: word or line fallback`
  If exact character matching fails, the backend falls back to a broader bbox:
  for OCR content, it unions overlapping OCR word boxes;
  for PDFs, it unions the line containing the matched value or normalized version of the value.
- `Tier 3: null fallback`
  If neither exact nor broader matching succeeds, the finding is still returned with all metadata but `bbox: null`, allowing sidebar review without a misplaced overlay.
