import FindingCard from './FindingCard.jsx'
import RiskBadge from './RiskBadge.jsx'

export default function FindingsPanel({ findings, maskedIds, onToggle, riskScore }) {
  return (
    <aside className="findings-panel">
      <RiskBadge riskScore={riskScore} />
      <div className="findings-heading">
        <div>
          <p className="eyebrow">Review queue</p>
          <h2>Detected findings</h2>
        </div>
        <span>{findings.length} total</span>
      </div>
      <div className="findings-list">
        {findings.map((finding) => (
          <FindingCard
            key={finding.id}
            finding={finding}
            isMasked={maskedIds.has(finding.id)}
            onToggle={() => onToggle(finding.id)}
          />
        ))}
      </div>
    </aside>
  )
}
