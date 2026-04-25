export default function FindingCard({ finding, isMasked, onToggle }) {
  return (
    <article className="finding-card">
      <div className="finding-card-top">
        <div>
          <p className="finding-type">{finding.type.toUpperCase()}</p>
          <h3>{finding.value}</h3>
        </div>
        <span className={`severity-pill is-${finding.severity}`}>{finding.severity}</span>
      </div>
      <div className="finding-card-bottom">
        <p>
          Page {finding.page}
          {finding.bbox ? '' : ' • Sidebar only'}
        </p>
        <button type="button" className={`toggle-chip ${isMasked ? 'is-on' : ''}`} onClick={onToggle}>
          {isMasked ? 'Masked' : 'Mask'}
        </button>
      </div>
    </article>
  )
}
