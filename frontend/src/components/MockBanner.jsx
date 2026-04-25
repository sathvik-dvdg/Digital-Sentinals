export default function MockBanner({ visible }) {
  if (!visible) {
    return null
  }

  return (
    <div className="mock-banner">
      Mock mode is active. The review flow is running from local demo data and won&apos;t call the backend.
    </div>
  )
}
