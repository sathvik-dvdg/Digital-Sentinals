# agents.md — PII Shield MVP: Multi-Agent Workflow Specification

> **Version:** 1.0.0  
> **Product:** PII Shield — Document PII Detection & Redaction Tool  
> **Stack:** React 18 + Vite + Tailwind | FastAPI (single `main.py`) | Regex PII Engine  
> **Scope:** Hackathon MVP — 20-hour build window  
> **This file is the single source of truth for all AI agents.**

---

## 1. SYSTEM OVERVIEW

### Product Description

PII Shield is a privacy-first, client-side document scanner that detects and redacts Personally Identifiable Information (PII) from uploaded PDF, PNG, and JPG files. It runs entirely on localhost — no data is retained after the session.

### High-Level Architecture

```
[Browser]
  UploadZone → useReducer state → POST /scan → ReviewScreen
  ReviewScreen → Mask toggles → POST /redact → Download PDF
  /health check → mock mode fallback if backend unavailable

[Backend: main.py (FastAPI)]
  /health  →  liveness check
  /scan    →  detect file type → extract text+coords → PII regex → normalize bboxes → rasterize pages → return JSON
  /redact  →  re-extract file → look up bboxes by finding_id → draw black rects → return PDF blob

[Processing Layer]
  PIIEngine    — 4 regex patterns (Aadhaar, PAN, phone, email)
  BboxMapper   — 3-tier fallback: exact char → word/line → null
  Preprocessor — autocontrast only (no denoising)
```

### Key Constraints (MVP — Do Not Violate)

- No database, no session store, no auth, no cloud deploy
- File is re-sent on `/redact` — no server-side state between requests
- Maximum 3 pages rasterized per document
- All bboxes are normalized (0.0–1.0 ratios) — no raw pixel math on the frontend
- No ML/LLM in the pipeline — regex only
- No DOCX support
- Backend must fail gracefully — mock mode must activate automatically

---

## 2. GLOBAL RULES (MANDATORY FOR ALL AGENTS)

All agents **must** follow these rules without exception. Any output violating these rules must be regenerated before the next agent consumes it.

### R1 — Output Format
- Every agent output must be structured Markdown with clearly labeled sections
- Code outputs must be complete, runnable files — no pseudocode, no `// TODO` stubs
- Schema outputs must use TypeScript interfaces or explicit JSON structures with types annotated

### R2 — No Assumptions
- Agents must not invent fields, endpoints, or behaviors not defined in this file or in upstream agent outputs
- If an input is ambiguous, the agent must flag it explicitly under a `## AMBIGUITIES` section and halt — not guess

### R3 — Contract Adherence
- Every API endpoint implemented by Agent 3 must match the API Contract defined in Section 3 exactly
- Every frontend component built by Agent 5 must consume APIs exactly as defined — no shape mutations
- Every data structure must conform to the Data Model defined in Section 3

### R4 — No Placeholder Data
- No `"example.com"`, `"John Doe"`, `"TODO"`, `"lorem ipsum"` in any output
- Mock data (for demo mode) must use the exact schema defined in Section 3 and reference realistic but fake Indian PII patterns (e.g., `ABCDE1234F` for PAN)

### R5 — Implementation-Ready Outputs
- Every output must be directly committable to the repository
- Imports must be real and resolvable given the defined stack
- All file paths must follow the project structure defined in Section 3

### R6 — Dependency Order
- An agent must not begin work until all upstream dependencies (defined per task in Section 5) are marked `COMPLETE`
- Outputs are passed by writing structured files into the shared `/outputs/` contract directory

---

## 3. SHARED CONTRACTS

These contracts are **immutable** during the MVP build. No agent may alter them unilaterally. Changes require explicit re-versioning of this file.

---

### 3.1 Project File Structure

```
pii-shield/
├── backend/
│   └── main.py                  # Single FastAPI file — all endpoints here
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── state/
│   │   │   └── appReducer.js    # useReducer definitions
│   │   ├── components/
│   │   │   ├── UploadZone.jsx
│   │   │   ├── ScanningOverlay.jsx
│   │   │   ├── DocumentViewer.jsx
│   │   │   ├── RedactionOverlay.jsx
│   │   │   ├── FindingsPanel.jsx
│   │   │   ├── FindingCard.jsx
│   │   │   ├── RiskBadge.jsx
│   │   │   ├── ActionBar.jsx
│   │   │   ├── MockBanner.jsx
│   │   │   └── CompletionScreen.jsx
│   │   └── mock/
│   │       └── mock_response.json
│   ├── vite.config.js
│   └── package.json
└── agents.md                    # This file
```

---

### 3.2 API Contracts

#### `GET /health`

```
Request: none

Response 200:
{
  "status": "ok",
  "ocr_available": boolean,
  "version": "1.0.0"
}
```

---

#### `POST /scan`

```
Request: multipart/form-data
  file: binary   // PDF | PNG | JPEG, max 10MB

Response 200:
{
  "mode": "pdf_text" | "ocr_image",
  "page_count": number,
  "pages": [
    {
      "page_number": number,       // 1-indexed
      "image_b64": string,         // base64-encoded PNG, max width 1000px
      "width": number,             // rendered pixel width
      "height": number             // rendered pixel height
    }
  ],
  "findings": [
    {
      "id": string,                // UUID v4
      "type": "aadhaar" | "pan" | "phone" | "email",
      "value": string,             // masked: "XXXX-XXXX-3456"
      "raw_value": string,         // full matched string (never sent to frontend display)
      "page": number,              // 1-indexed
      "severity": "high" | "medium",
      "confidence": number,        // 0.0–1.0
      "bbox": {
        "x": number,               // normalized 0.0–1.0 (left edge)
        "y": number,               // normalized 0.0–1.0 (top edge)
        "w": number,               // normalized width
        "h": number                // normalized height
      } | null                     // null = Tier 3 fallback, no overlay rendered
    }
  ],
  "risk_score": {
    "level": "HIGH" | "MEDIUM" | "SAFE",
    "total_findings": number,
    "high_count": number,
    "medium_count": number
  }
}

Response 400: { "error": "unsupported_file_type" | "file_too_large" | "no_text_extracted" }
Response 500: { "error": "processing_failed", "detail": string }
```

---

#### `POST /redact`

```
Request: multipart/form-data
  file: binary          // Same file re-uploaded
  finding_ids: string   // JSON array of UUID strings, e.g. '["uuid1","uuid2"]'

Response 200:
  Content-Type: application/pdf
  Body: PDF binary blob

Response 400: { "error": "invalid_finding_ids" | "file_mismatch" }
Response 500: { "error": "redaction_failed", "detail": string }
```

---

### 3.3 Frontend State Contract

**Defined in:** `frontend/src/state/appReducer.js`

```typescript
type Phase = 'upload' | 'scanning' | 'review' | 'downloading' | 'complete';

interface AppState {
  phase: Phase;
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

---

### 3.4 Component Contracts

Each component's props are fixed. Agents must not add, remove, or rename props.

| Component | Props | State | API Dependency |
|---|---|---|---|
| `UploadZone` | `onFile: (file: File) => void` | none | none |
| `ScanningOverlay` | `slowWarning: boolean` | none | none |
| `DocumentViewer` | `pages: Page[], findings: Finding[], maskedIds: Set<string>` | none | none |
| `RedactionOverlay` | `finding: Finding, isMasked: boolean` | none | none |
| `FindingsPanel` | `findings: Finding[], maskedIds: Set<string>, onToggle: (id: string) => void, riskScore: RiskScore` | none | none |
| `FindingCard` | `finding: Finding, isMasked: boolean, onToggle: () => void` | none | none |
| `RiskBadge` | `riskScore: RiskScore` | none | none |
| `ActionBar` | `onMaskAll: () => void, onDownload: () => void, downloading: boolean, allMasked: boolean` | none | none |
| `MockBanner` | `visible: boolean` | none | none |
| `CompletionScreen` | `onReset: () => void` | none | none |

---

### 3.5 PII Regex Patterns (Canonical — Do Not Alter)

```python
PII_PATTERNS = {
    "aadhaar": r"\b[2-9]{1}[0-9]{3}\s[0-9]{4}\s[0-9]{4}\b",
    "pan":     r"\b[A-Z]{5}[0-9]{4}[A-Z]{1}\b",
    "phone":   r"\b(?:\+91[\-\s]?)?[6-9]\d{9}\b",
    "email":   r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"
}

SEVERITY_MAP = {
    "aadhaar": "high",
    "pan":     "high",
    "phone":   "medium",
    "email":   "medium"
}
```

---

### 3.6 Mock Response Contract

**File:** `frontend/src/mock/mock_response.json`  
Must be a valid `ScanResponse` object (matching Section 3.2) with at least:
- 1 page with a valid `image_b64` (a real base64 PNG string, not placeholder)
- 2 findings: one Aadhaar (high), one email (medium)
- `risk_score.level: "HIGH"`
- All bboxes present (not null)

---

## 4. AGENT DEFINITIONS

---

### Agent 1 — Product Analyst

**Role:** Translates the feature list into ranked, unambiguous requirements. Owns the user flow document. Does not produce code.

**Input:**
- Raw feature list (from this file, Section 0 context)
- Architecture overview (Section 1)

**Output:** `outputs/A1_requirements.md`

**Responsibilities:**
- Categorize features as: Must Have / Should Have / Won't Have (MVP)
- Define user flows as numbered steps (no diagrams, text only)
- Define acceptance criteria per feature (testable, binary pass/fail)
- Flag any feature that conflicts with architectural constraints

**Must Not:**
- Invent features not in the input list
- Produce code or schemas
- Mark excluded features as in-scope

---

### Agent 2 — System Architect

**Role:** Owns the technical architecture. Validates that the architecture is correctly understood and documented. Does not produce code.

**Input:** `outputs/A1_requirements.md`

**Output:** `outputs/A2_architecture.md`

**Responsibilities:**
- Confirm the component diagram matches the architecture in Section 1
- Define inter-component data flow with explicit payload types (reference Section 3.2)
- Define the 3-tier BboxMapper fallback logic in prose (not code)
- Define error states and their frontend handling
- Confirm mock mode activation conditions

**Must Not:**
- Change the API contracts defined in Section 3
- Introduce new components not in the component tree (Section 3)
- Recommend databases, session stores, or external services

---

### Agent 3 — Backend Engineer

**Role:** Implements `backend/main.py` in full. Owns all backend logic.

**Input:** `outputs/A2_architecture.md`, Section 3.2 (API Contracts), Section 3.5 (Regex Patterns)

**Output:** `backend/main.py` (complete, runnable file)

**Responsibilities:**
- Implement `/health`, `/scan`, `/redact` exactly per Section 3.2
- Implement `PIIEngine` using patterns from Section 3.5
- Implement `BboxMapper` with all 3 tiers
- Implement `Preprocessor` (autocontrast only — no denoising)
- Return normalized bboxes (0.0–1.0)
- Cap rasterization at 3 pages, max 1000px width
- Use in-memory `scan_cache: dict` keyed by `(file_hash, finding_id)` for `/redact` bbox lookup
- Handle all 400 and 500 error cases defined in Section 3.2

**Must Not:**
- Add a database or persistent session store
- Add endpoints not defined in Section 3.2
- Use ML libraries (no spaCy, no transformers, no presidio)
- Return raw PII values in the `value` field (must be masked)

---

### Agent 4 — ML Engineer

**Status: EXCLUDED from this MVP.**

Rationale: PII patterns are structurally rigid (fixed formats). Regex achieves equivalent accuracy with zero latency overhead and no failure modes. ML is explicitly excluded per architecture constraints.

If included in a future version, Agent 4 would own the model interface between a NER model output and the `Finding` schema in Section 3.2.

---

### Agent 5 — Frontend Engineer

**Role:** Implements all React components and application state. Owns the entire `frontend/src/` directory.

**Input:** `outputs/A2_architecture.md`, Section 3.2 (API Contracts), Section 3.3 (State Contract), Section 3.4 (Component Contracts)

**Output:** All files under `frontend/src/` (complete, runnable)

**Responsibilities:**
- Implement `appReducer.js` exactly per Section 3.3
- Implement all components per Section 3.4
- Implement `RedactionOverlay` using normalized bbox rendering (code in Section 8, architecture doc)
- Implement `/health` check on mount → set `mockMode: true` if check fails or returns non-200
- Implement slow-scan warning: `SCAN_SLOW` action dispatched if `/scan` takes > 3 seconds
- Implement mock fallback: if `mockMode`, use `mock_response.json` instead of calling `/scan`
- Keyboard shortcut `Ctrl+Shift+D` forces mock mode
- Configure Vite proxy: `/api` → `http://localhost:8000`

**Must Not:**
- Add components not in the tree defined in Section 3.4
- Mutate the `ScanResponse` shape received from the API
- Store file content in localStorage or sessionStorage
- Call `/scan` or `/redact` when in mock mode (except a silenced no-op)

---

### Agent 6 — Integration Engineer

**Role:** Validates end-to-end compatibility between Agent 3 and Agent 5 outputs. Produces a validation report and a runnable integration test script. Does not write application code.

**Input:** `backend/main.py`, `frontend/src/` (all files), Section 3 (all contracts)

**Output:** `outputs/A6_integration_report.md`, `outputs/test_integration.py`

**Responsibilities:**
- Verify every field returned by `/scan` is consumed correctly in `FindingsPanel` and `DocumentViewer`
- Verify `maskedIds` passed to `POST /redact` matches the `finding_ids` schema
- Verify bbox normalization: backend outputs 0.0–1.0 floats, frontend uses `* 100` for `%`
- Verify mock mode activates when `/health` fails
- Verify risk score computation matches finding counts
- Write `test_integration.py`: pytest tests that spin up FastAPI with `TestClient`, upload a real sample PDF, and assert response shape

**Must Not:**
- Modify application code to fix issues — must only report them for Agent 3 or Agent 5 to fix
- Skip validation of any contract field defined in Section 3

---

## 5. TASK BREAKDOWN (SEQUENTIAL EXECUTION)

---

### Task A1 — Product Analysis

| Field | Value |
|---|---|
| **Task ID** | A1 |
| **Agent** | Agent 1 — Product Analyst |
| **Objective** | Produce ranked requirements and acceptance criteria for the MVP feature set |
| **Inputs** | Feature list (this file, preamble), Architecture overview (Section 1) |
| **Output File** | `outputs/A1_requirements.md` |
| **Output Schema** | `## Features\n### Must Have\n- [feature]: [acceptance criterion]\n### Won't Have (MVP)\n- [feature]: [reason]\n## User Flows\n### [Flow Name]\n1. [step]\n## Constraints Confirmed` |
| **Dependencies** | None |
| **Blocking** | A2 cannot start until A1 is marked COMPLETE |

---

### Task A2 — Architecture Design

| Field | Value |
|---|---|
| **Task ID** | A2 |
| **Agent** | Agent 2 — System Architect |
| **Objective** | Confirm architecture alignment and define data flow with explicit payload types |
| **Inputs** | `outputs/A1_requirements.md`, Section 1, Section 3 |
| **Output File** | `outputs/A2_architecture.md` |
| **Output Schema** | `## Component Diagram (text)\n## Data Flow (annotated with payload types)\n## Error States\n## Mock Mode Conditions\n## BboxMapper Fallback Logic` |
| **Dependencies** | A1 COMPLETE |
| **Blocking** | A3 and A5 cannot start until A2 is marked COMPLETE |

---

### Task A3 — Backend Implementation

| Field | Value |
|---|---|
| **Task ID** | A3 |
| **Agent** | Agent 3 — Backend Engineer |
| **Objective** | Implement complete `backend/main.py` with all endpoints, PII engine, bbox mapper |
| **Inputs** | `outputs/A2_architecture.md`, Section 3.2, Section 3.5 |
| **Output File** | `backend/main.py` |
| **Output Schema** | Single Python file. Must be runnable with: `uvicorn main:app --reload`. Must pass: `curl http://localhost:8000/health` |
| **Dependencies** | A2 COMPLETE |
| **Blocking** | A6 cannot start until A3 is marked COMPLETE |

---

### Task A5 — Frontend Implementation

| Field | Value |
|---|---|
| **Task ID** | A5 |
| **Agent** | Agent 5 — Frontend Engineer |
| **Objective** | Implement all React components, app state, API integration, and mock mode |
| **Inputs** | `outputs/A2_architecture.md`, Section 3.2, Section 3.3, Section 3.4 |
| **Output Files** | All files under `frontend/src/`, `frontend/vite.config.js`, `frontend/package.json` |
| **Output Schema** | Must be runnable with: `npm install && npm run dev`. App must load at `http://localhost:5173` |
| **Dependencies** | A2 COMPLETE (A3 can be in progress — mock mode allows parallel dev) |
| **Blocking** | A6 cannot start until A5 is marked COMPLETE |

---

### Task A6 — Integration Validation

| Field | Value |
|---|---|
| **Task ID** | A6 |
| **Agent** | Agent 6 — Integration Engineer |
| **Objective** | Validate full end-to-end contract compliance between backend and frontend |
| **Inputs** | `backend/main.py`, all `frontend/src/` files, Section 3 |
| **Output Files** | `outputs/A6_integration_report.md`, `outputs/test_integration.py` |
| **Output Schema** | Report: `## Checks\n| Check | Status | Notes |\n`. Test file: pytest runnable with `pytest outputs/test_integration.py` |
| **Dependencies** | A3 COMPLETE, A5 COMPLETE |
| **Blocking** | Build is not considered MVP-ready until A6 passes all checks |

---

## 6. EXECUTION FLOW

```
[A1] Product Analysis
        ↓ outputs/A1_requirements.md
[A2] Architecture Design
        ↓ outputs/A2_architecture.md
       / \
      /   \
[A3]       [A5]        ← Parallel execution permitted
Backend    Frontend
main.py    src/
      \   /
       \ /
[A6] Integration Validation
        ↓ A6_integration_report.md + test_integration.py
[✓] MVP Build Complete
```

### Output Passing Protocol

1. Each agent writes its output to the file path defined in its task (Section 5)
2. Before consuming an upstream output, the consuming agent must verify the output file exists and contains all required sections (defined in the Output Schema column)
3. If a required section is missing, the consuming agent must halt and emit: `BLOCKED: [Task ID] output is missing section: [section name]`

### Validation Checkpoints

| Checkpoint | After Task | Gate Condition |
|---|---|---|
| CP1 | A1 | All MVP features have acceptance criteria. All excluded features have stated reasons. |
| CP2 | A2 | Data flow covers all 3 API endpoints. All error states are named. BboxMapper tiers are described. |
| CP3 | A3 | `/health` returns `{"status":"ok"}`. `/scan` with a test PDF returns valid `ScanResponse` shape. |
| CP4 | A5 | App loads. Upload zone accepts a PDF. Mock mode activates via `Ctrl+Shift+D`. |
| CP5 | A6 | All rows in `A6_integration_report.md` show `PASS`. `test_integration.py` exits 0. |

---

## 7. VALIDATION LAYER

The following rules are checked by Agent 6. Any failure blocks the MVP from being considered complete.

### V1 — API Shape Consistency
- Every field in `ScanResponse` (Section 3.2) must be present in the backend response
- Every field consumed by the frontend must exist in `ScanResponse`
- No frontend component may access a field not defined in Section 3.2

### V2 — Bbox Coordinate Consistency
- Backend must return `bbox.x`, `bbox.y`, `bbox.w`, `bbox.h` as floats in `[0.0, 1.0]`
- `RedactionOverlay` must render using `bbox.x * 100` as `left` percentage (no raw pixel values)
- A finding with `bbox: null` must render with no overlay div (sidebar entry only)

### V3 — Finding ID Roundtrip
- Every `finding.id` returned by `/scan` must be a valid UUID v4
- `/redact` must accept an array of those UUIDs via `finding_ids` field
- Backend must reconstruct bboxes from the in-memory cache using those IDs, not from the frontend payload

### V4 — Risk Score Accuracy
- `risk_score.high_count` must equal the count of findings where `severity === "high"`
- `risk_score.level` must be: `"HIGH"` if `high_count > 0`, `"MEDIUM"` if `medium_count > 0 && high_count === 0`, `"SAFE"` otherwise
- Frontend `RiskBadge` must reflect the same logic when computing display state from `maskedIds`

### V5 — Mock Mode Integrity
- When `mockMode: true`, frontend must not fire real `/scan` or `/redact` requests
- Mock response must conform to `ScanResponse` schema (Section 3.2) — validated by Agent 6 via JSON schema check
- Slow warning (`SCAN_SLOW`) must not appear in mock mode

### V6 — No Data Retention
- Backend must not write any uploaded file or extracted text to disk
- Backend must not log raw PII values
- Backend `scan_cache` must store only `{finding_id: bbox_coords}` — no raw text, no file content

---

## 8. FAILURE HANDLING

### 8.1 Incomplete Agent Output

If an agent produces an output file that is missing required sections (per Section 5 Output Schema):

1. **Do not proceed.** The downstream agent must not consume a partial output.
2. **Emit a BLOCKED message:** `BLOCKED: Task [ID] — missing: [section list]`
3. **Regenerate:** Re-run the failing agent with the same inputs. Do not modify the inputs.
4. **If regeneration fails twice:** Escalate by reducing the output scope — flag non-critical sections as `DEFERRED` and ensure all contract-critical sections (schemas, endpoints, state) are complete before unblocking.

### 8.2 Contract Mismatch

If Agent 6 reports a mismatch between backend and frontend on a shared contract field:

1. **Identify the source of truth:** Section 3 is always authoritative.
2. **Fix the deviating agent:** The agent whose output deviates from Section 3 must be regenerated — not the contract.
3. **Do not modify Section 3 contracts** to accommodate a wrong implementation.

### 8.3 Runtime Failures (Demo)

| Failure | Recovery |
|---|---|
| Backend unreachable at `/health` | Frontend auto-activates mock mode. No user action needed. |
| `/scan` timeout (> 8 seconds) | Frontend dispatches `SCAN_ERROR`. Mock fallback activates. |
| `/redact` fails | Frontend shows error toast. "Download" button re-enables. User retries. |
| OCR produces garbage text | Backend returns findings with low confidence scores. Frontend shows "Low clarity" warning. Still renders partial results. |
| BboxMapper Tier 1 and Tier 2 fail | Finding returned with `bbox: null`. Sidebar entry shown, no overlay rendered. |
| Everything fails | `Ctrl+Shift+D` forces perfect mock mode. Demonstrates full UI flow. |

### 8.4 Conflict Resolution

If two agents produce outputs that are mutually incompatible (e.g., Agent 3 returns a field name different from what Agent 5 consumes):

1. Compare both outputs against Section 3 contracts
2. The output that deviates from Section 3 is wrong — regenerate that agent's output only
3. Never resolve conflicts by changing both outputs to a third shape not in Section 3

---

## 9. FINAL OUTPUT FORMAT

When the full build is complete, the repository must contain exactly the following deliverables. Each item is the direct, implementation-ready output of the responsible agent.

| File | Responsible Agent | Verified By |
|---|---|---|
| `outputs/A1_requirements.md` | Agent 1 | Agent 2 (consumed as input) |
| `outputs/A2_architecture.md` | Agent 2 | Agents 3, 5 (consumed as input) |
| `backend/main.py` | Agent 3 | Agent 6 (integration test) |
| `frontend/src/state/appReducer.js` | Agent 5 | Agent 6 |
| `frontend/src/components/*.jsx` | Agent 5 | Agent 6 |
| `frontend/src/App.jsx` | Agent 5 | Agent 6 |
| `frontend/src/mock/mock_response.json` | Agent 5 | Agent 6 (schema check) |
| `frontend/vite.config.js` | Agent 5 | Manual (proxy config) |
| `frontend/package.json` | Agent 5 | Manual (deps check) |
| `outputs/A6_integration_report.md` | Agent 6 | Human reviewer |
| `outputs/test_integration.py` | Agent 6 | CI (`pytest`) |

### Definition of Done

The MVP is complete when:

- [ ] `pytest outputs/test_integration.py` exits 0
- [ ] `uvicorn main:app --reload` starts without error
- [ ] `npm run dev` starts without error
- [ ] Uploading a PDF with Aadhaar/PAN returns findings with colored overlays
- [ ] "Mask All" turns all overlays solid black and risk badge turns green
- [ ] "Download Safe Copy" produces a PDF with black rectangles over all PII
- [ ] Killing the backend and refreshing the page activates mock mode automatically
- [ ] `Ctrl+Shift+D` activates mock mode with a complete demo flow

---

*End of agents.md — PII Shield MVP v1.0.0*
