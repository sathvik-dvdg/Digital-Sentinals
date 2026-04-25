import { useRef, useState } from 'react'

export default function UploadZone({ onFile }) {
  const inputRef = useRef(null)
  const [dragActive, setDragActive] = useState(false)

  function handleFiles(fileList) {
    const [file] = Array.from(fileList ?? [])
    if (file) {
      onFile(file)
    }
  }

  function onDrop(event) {
    event.preventDefault()
    setDragActive(false)
    handleFiles(event.dataTransfer.files)
  }

  return (
    <section className="upload-shell">
      <div
        className={`upload-zone ${dragActive ? 'is-active' : ''}`}
        onClick={() => inputRef.current?.click()}
        onDragEnter={(event) => {
          event.preventDefault()
          setDragActive(true)
        }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={(event) => {
          event.preventDefault()
          setDragActive(false)
        }}
        onDrop={onDrop}
        role="button"
        tabIndex={0}
        onKeyDown={(event) => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault()
            inputRef.current?.click()
          }
        }}
      >
        <div className="upload-badge">Offline-first scan</div>
        <h1>PII Shield</h1>
        <p className="upload-copy">
          Drop a PDF, PNG, or JPG to detect Aadhaar, PAN, phone, and email data locally.
        </p>
        <div className="upload-actions">
          <button type="button" className="primary-button">
            Choose Document
          </button>
          <span>or drag it here</span>
        </div>
        <ul className="upload-meta">
          <li>Single file only</li>
          <li>10 MB max</li>
          <li>Preview capped at 3 pages</li>
        </ul>
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg"
          hidden
          onChange={(event) => handleFiles(event.target.files)}
        />
      </div>
    </section>
  )
}
