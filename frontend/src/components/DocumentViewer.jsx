import RedactionOverlay from './RedactionOverlay.jsx'

export default function DocumentViewer({ pages, findings, maskedIds }) {
  return (
    <section className="viewer-panel">
      {pages.map((page) => {
        const pageFindings = findings.filter((finding) => finding.page === page.page_number)

        return (
          <article key={page.page_number} className="page-card">
            <header className="page-card-header">
              <span>Page {page.page_number}</span>
              <span>
                {page.width} x {page.height}
              </span>
            </header>
            <div className="page-frame">
              <img
                src={`data:image/png;base64,${page.image_b64}`}
                alt={`Document preview page ${page.page_number}`}
                className="page-image"
              />
              {pageFindings.map((finding) => (
                <RedactionOverlay
                  key={finding.id}
                  finding={finding}
                  isMasked={maskedIds.has(finding.id)}
                />
              ))}
            </div>
          </article>
        )
      })}
    </section>
  )
}
