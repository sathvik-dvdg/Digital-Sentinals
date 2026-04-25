export default function CompletionScreen({ onReset }) {
  return (
    <section className="completion-shell">
      <div className="completion-card">
        <p className="eyebrow">Safe copy generated</p>
        <h1>1 Document Secured.</h1>
        <p className="completion-copy">0 bytes retained. Your next scan starts from a clean session.</p>
        <button type="button" className="primary-button" onClick={onReset}>
          Scan Another Document
        </button>
      </div>
    </section>
  )
}
