import { useEffect, useMemo, useReducer } from 'react'
import ActionBar from './components/ActionBar.jsx'
import CompletionScreen from './components/CompletionScreen.jsx'
import DocumentViewer from './components/DocumentViewer.jsx'
import FindingsPanel from './components/FindingsPanel.jsx'
import MockBanner from './components/MockBanner.jsx'
import ScanningOverlay from './components/ScanningOverlay.jsx'
import UploadZone from './components/UploadZone.jsx'
import mockResponse from './mock/mock_response.json'
import { appReducer, initialState } from './state/appReducer.js'

const SLOW_WARNING_MS = 3000
const HARD_TIMEOUT_MS = 8000
const MOCK_PDF_BASE64 =
  'JVBERi0xLjEKMSAwIG9iago8PCAvVHlwZSAvQ2F0YWxvZyAvUGFnZXMgMiAwIFIgPj4KZW5kb2JqCjIgMCBvYmoKPDwgL1R5cGUgL1BhZ2VzIC9LaWRzIFszIDAgUl0gL0NvdW50IDEgPj4KZW5kb2JqCjMgMCBvYmoKPDwgL1R5cGUgL1BhZ2UgL1BhcmVudCAyIDAgUiAvTWVkaWFCb3ggWzAgMCAzMDAgMTQ0XSAvQ29udGVudHMgNCAwIFIgL1Jlc291cmNlcyA8PCAvRm9udCA8PCAvRjEgNSAwIFIgPj4gPj4gPj4KZW5kb2JqCjQgMCBvYmoKPDwgL0xlbmd0aCA1MyA+PgpzdHJlYW0KQlQKL0YxIDE4IFRmCjQwIDcyIFRkCihQSUkgU2hpZWxkIE1vY2sgQ29weSkgVGoKRVQKZW5kc3RyZWFtCmVuZG9iago1IDAgb2JqCjw8IC9UeXBlIC9Gb250IC9TdWJ0eXBlIC9UeXBlMSAvQmFzZUZvbnQgL0hlbHZldGljYSA+PgplbmRvYmoKeHJlZgowIDYKMDAwMDAwMDAwMCA2NTUzNSBmIAowMDAwMDAwMDEwIDAwMDAwIG4gCjAwMDAwMDAwNjAgMDAwMDAgbiAKMDAwMDAwMDExNyAwMDAwMCBuIAowMDAwMDAwMjQyIDAwMDAwIG4gCjAwMDAwMDAzNDQgMDAwMDAgbiAKdHJhaWxlcgo8PCAvU2l6ZSA2IC9Sb290IDEgMCBSID4+CnN0YXJ0eHJlZgo0MTQKJSVFT0Y='

function validateFile(file) {
  if (!file) {
    return 'Choose a document to continue.'
  }
  if (file.size > 10 * 1024 * 1024) {
    return 'File exceeds the 10 MB limit.'
  }

  const lowerName = file.name.toLowerCase()
  if (
    !(
      lowerName.endsWith('.pdf') ||
      lowerName.endsWith('.png') ||
      lowerName.endsWith('.jpg') ||
      lowerName.endsWith('.jpeg')
    )
  ) {
    return 'Unsupported file type. Use PDF, PNG, or JPG.'
  }

  return null
}

function deriveRiskScore(findings, maskedIds) {
  const activeFindings = findings.filter((finding) => !maskedIds.has(finding.id))
  const highCount = activeFindings.filter((finding) => finding.severity === 'high').length
  const mediumCount = activeFindings.filter((finding) => finding.severity === 'medium').length

  let level = 'SAFE'
  if (highCount > 0) {
    level = 'HIGH'
  } else if (mediumCount > 0) {
    level = 'MEDIUM'
  }

  return {
    level,
    total_findings: activeFindings.length,
    high_count: highCount,
    medium_count: mediumCount,
  }
}

function decodeBase64ToBlob(base64, mimeType) {
  const binary = window.atob(base64)
  const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0))
  return new Blob([bytes], { type: mimeType })
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

function buildDownloadName(fileName) {
  const cleaned = fileName.replace(/\.[^.]+$/, '') || 'pii-shield'
  return `${cleaned}-safe-copy.pdf`
}

export default function App() {
  const [state, dispatch] = useReducer(appReducer, initialState)

  useEffect(() => {
    let ignore = false

    async function checkHealth() {
      try {
        const response = await fetch('/api/health')
        if (!response.ok && !ignore) {
          dispatch({ type: 'SET_MOCK', enabled: true })
        }
      } catch {
        if (!ignore) {
          dispatch({ type: 'SET_MOCK', enabled: true })
        }
      }
    }

    checkHealth()

    return () => {
      ignore = true
    }
  }, [])

  useEffect(() => {
    function onKeyDown(event) {
      if (event.ctrlKey && event.shiftKey && event.key.toLowerCase() === 'd') {
        dispatch({ type: 'SET_MOCK', enabled: true })
      }
    }

    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  const findings = state.scanResult?.findings ?? []
  const pages = state.scanResult?.pages ?? []
  const allMasked = findings.length > 0 && findings.every((finding) => state.maskedIds.has(finding.id))
  const displayRiskScore = useMemo(
    () => deriveRiskScore(findings, state.maskedIds),
    [findings, state.maskedIds],
  )

  async function loadMockFlow(file) {
    dispatch({ type: 'START_SCAN', file })
    window.setTimeout(() => {
      dispatch({ type: 'SCAN_SUCCESS', result: mockResponse })
    }, 250)
  }

  async function handleFile(file) {
    const validationError = validateFile(file)
    if (validationError) {
      dispatch({ type: 'SCAN_ERROR', error: validationError })
      return
    }

    if (state.mockMode) {
      loadMockFlow(file)
      return
    }

    dispatch({ type: 'START_SCAN', file })

    const controller = new AbortController()
    const slowTimer = window.setTimeout(() => dispatch({ type: 'SCAN_SLOW' }), SLOW_WARNING_MS)
    const hardTimer = window.setTimeout(() => controller.abort(), HARD_TIMEOUT_MS)

    try {
      const formData = new FormData()
      formData.append('file', file)

      const response = await fetch('/api/scan', {
        method: 'POST',
        body: formData,
        signal: controller.signal,
      })

      window.clearTimeout(slowTimer)
      window.clearTimeout(hardTimer)

      if (!response.ok) {
        const errorPayload = await response.json().catch(() => null)
        dispatch({
          type: 'SCAN_ERROR',
          error: errorPayload?.error ? `Scan failed: ${errorPayload.error}` : 'Scan failed.',
        })
        return
      }

      const result = await response.json()
      dispatch({ type: 'SCAN_SUCCESS', result })
    } catch (error) {
      window.clearTimeout(slowTimer)
      window.clearTimeout(hardTimer)

      const message =
        error?.name === 'AbortError'
          ? 'Live scan timed out. Switched to mock mode.'
          : 'Live scan unavailable. Switched to mock mode.'

      dispatch({ type: 'SCAN_ERROR', error: message })
      dispatch({ type: 'SET_MOCK', enabled: true })
      loadMockFlow(file)
    }
  }

  function handleMaskAll() {
    dispatch({ type: allMasked ? 'UNMASK_ALL' : 'MASK_ALL' })
  }

  async function handleDownload() {
    if (!state.file || !state.scanResult) {
      return
    }

    if (state.maskedIds.size === 0) {
      window.alert('Mask at least one finding before downloading a safe copy.')
      return
    }

    dispatch({ type: 'START_DOWNLOAD' })

    if (state.mockMode) {
      const blob = decodeBase64ToBlob(MOCK_PDF_BASE64, 'application/pdf')
      downloadBlob(blob, buildDownloadName(state.file.name))
      dispatch({ type: 'DOWNLOAD_DONE' })
      return
    }

    try {
      const formData = new FormData()
      formData.append('file', state.file)
      formData.append('finding_ids', JSON.stringify(Array.from(state.maskedIds)))

      const response = await fetch('/api/redact', {
        method: 'POST',
        body: formData,
      })

      if (!response.ok) {
        const errorPayload = await response.json().catch(() => null)
        throw new Error(errorPayload?.error || 'redaction_failed')
      }

      const blob = await response.blob()
      downloadBlob(blob, buildDownloadName(state.file.name))
      dispatch({ type: 'DOWNLOAD_DONE' })
    } catch (error) {
      dispatch({ type: 'SCAN_SUCCESS', result: state.scanResult })
      window.alert(`Download failed: ${error.message}`)
    }
  }

  function handleReset() {
    dispatch({ type: 'RESET' })
  }

  const isReviewPhase = state.phase === 'review' || state.phase === 'downloading'
  const previewNote =
    state.scanResult && state.scanResult.page_count > state.scanResult.pages.length
      ? `Showing ${state.scanResult.pages.length} of ${state.scanResult.page_count} pages.`
      : 'All previewable pages are shown.'

  return (
    <div className="app-shell">
      <MockBanner visible={state.mockMode} />
      <header className="topbar">
        <div>
          <p className="eyebrow">Privacy-first document workflow</p>
          <h2>Scan, review, and flatten redactions without leaving localhost.</h2>
        </div>
        <div className="status-stack">
          <span className="status-pill">{state.mockMode ? 'Mock mode' : 'Backend mode'}</span>
          {state.scanResult ? <span className="status-pill">Mode: {state.scanResult.mode}</span> : null}
        </div>
      </header>

      {state.phase === 'upload' ? (
        <>
          <UploadZone onFile={handleFile} />
          {state.error ? <div className="inline-error">{state.error}</div> : null}
        </>
      ) : null}

      {state.phase === 'scanning' ? <ScanningOverlay slowWarning={state.slowWarning} /> : null}

      {isReviewPhase ? (
        <section className="review-grid">
          <div className="review-main">
            <div className="review-header">
              <div>
                <p className="eyebrow">Review surface</p>
                <h1>{state.file?.name ?? 'Document ready'}</h1>
              </div>
              <div className="review-copy">
                <p>{previewNote}</p>
                {state.scanResult?.mode === 'ocr_image' ? (
                  <p className="low-clarity-note">OCR mode active. Double-check low-contrast scans before export.</p>
                ) : null}
              </div>
            </div>

            <DocumentViewer pages={pages} findings={findings} maskedIds={state.maskedIds} />
            <ActionBar
              onMaskAll={handleMaskAll}
              onDownload={handleDownload}
              downloading={state.phase === 'downloading'}
              allMasked={allMasked}
            />
          </div>

          <FindingsPanel
            findings={findings}
            maskedIds={state.maskedIds}
            onToggle={(id) => dispatch({ type: 'TOGGLE_MASK', findingId: id })}
            riskScore={displayRiskScore}
          />
        </section>
      ) : null}

      {state.phase === 'complete' ? <CompletionScreen onReset={handleReset} /> : null}
    </div>
  )
}
