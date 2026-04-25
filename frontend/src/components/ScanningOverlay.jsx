export default function ScanningOverlay({ slowWarning }) {
  return (
    <section className="scan-shell">
      <div className="scan-card">
        <div className="scan-spinner" aria-hidden="true" />
        <p className="eyebrow">Analyzing document</p>
        <h2>Scanning for exposed PII</h2>
        <p className="scan-copy">
          Extracting text, matching the regex engine, and lining up bounding boxes for review.
        </p>
        {slowWarning ? (
          <div className="scan-warning">Still processing. Large or image-heavy files can take a bit longer.</div>
        ) : null}
      </div>
    </section>
  )
}
