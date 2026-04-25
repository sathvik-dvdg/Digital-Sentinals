export default function RiskBadge({ riskScore }) {
  return (
    <div className={`risk-badge is-${riskScore.level.toLowerCase()}`}>
      <div>
        <p className="eyebrow">Live risk</p>
        <h3>{riskScore.level}</h3>
      </div>
      <div className="risk-stats">
        <span>{riskScore.total_findings} active</span>
        <span>{riskScore.high_count} high</span>
        <span>{riskScore.medium_count} medium</span>
      </div>
    </div>
  )
}
