## Checks

| Check | Status | Notes |
| --- | --- | --- |
| `GET /health` contract shape | PASS | `backend/main.py` returns `status`, `ocr_available`, and `version` exactly as defined in Section 3.2. |
| `POST /scan` response fields consumed by frontend | PASS | `frontend/src/App.jsx`, `DocumentViewer.jsx`, and `FindingsPanel.jsx` consume `mode`, `page_count`, `pages`, `findings`, and `risk_score` without renaming the API shape. |
| Findings sidebar consumption | PASS | `FindingsPanel.jsx` and `FindingCard.jsx` use `id`, `type`, `value`, `page`, `severity`, `confidence`, and `bbox` safely; `raw_value` is never displayed. |
| Normalized bbox rendering | PASS | `RedactionOverlay.jsx` renders `left`, `top`, `width`, and `height` via `bbox.* * 100` percentages and returns `null` when `bbox` is `null`. |
| Finding ID roundtrip | PASS | `App.jsx` submits `finding_ids` as a JSON array string built from `maskedIds`, and `backend/main.py` resolves IDs from `scan_cache[(file_hash, finding_id)]`. |
| Risk score display logic | PASS | `App.jsx` derives display risk from unmasked findings using the required `HIGH -> MEDIUM -> SAFE` precedence and passes the contract-shaped object into `RiskBadge`. |
| Mock mode activation from `/health` failure | PASS | `App.jsx` enables `mockMode` when the mount-time health check fails or returns non-200. |
| Mock mode request suppression | PASS | `App.jsx` bypasses live `/scan` and `/redact` calls when `mockMode` is true and uses local mock data plus a local demo PDF blob instead. |
| Slow warning disabled in mock mode | PASS | `appReducer.js` ignores `SCAN_SLOW` while `mockMode` is true, and the mock flow never schedules slow-warning timers. |
| Zero-retention cache discipline | PASS | `backend/main.py` stores only page plus bbox data in `scan_cache`; it does not write uploads or extracted text to disk. |
| Frontend production build | PASS | `npm.cmd run build -- --configLoader native` succeeded under the installed Vite 8 toolchain. |
| Pytest execution of backend integration tests | BLOCKED | This environment does not expose a working Python interpreter, so `outputs/test_integration.py` was authored but not executed here. |

## Notes

- The frontend build required Vite's native config loader in this sandbox because the default config-loader path hit a `spawn EPERM` restriction during config bundling.
- Backend runtime validation remains the only unexecuted step from the Definition of Done because Python is unavailable in this session.
