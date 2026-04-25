export default function RedactionOverlay({ finding, isMasked }) {
  if (!finding.bbox) return null;

  const { x, y, w, h } = finding.bbox;
  
  return (
    <div
      className={`redaction-overlay ${isMasked ? 'is-masked' : ''} is-${finding.severity}`}
      style={{
        left: `${x * 100}%`,
        top: `${y * 100}%`,
        width: `${w * 100}%`,
        height: `${h * 100}%`,
      }}
      title={`${finding.type.toUpperCase()}: ${isMasked ? 'Redacted' : 'Visible'}`}
      aria-hidden="true"
    />
  );
}
