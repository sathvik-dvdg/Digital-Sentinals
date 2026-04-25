import { Link } from 'react-router-dom'
import { SignedIn, SignedOut } from '@clerk/clerk-react'

const FEATURES = [
  {
    icon: '🔍',
    title: 'Smart Detection',
    desc: 'Regex-powered engine detects Aadhaar, PAN, phone numbers, and email addresses with 95%+ precision on clean documents.',
  },
  {
    icon: '🛡️',
    title: 'Zero Data Retention',
    desc: 'All processing happens in-memory. No file ever touches disk, no database, no cloud — your documents stay yours.',
  },
  {
    icon: '📄',
    title: 'PDF & Image Support',
    desc: 'Upload PDFs, PNGs, or JPEGs. Our OCR pipeline handles scanned documents, rotated images, and mixed orientations.',
  },
  {
    icon: '⚡',
    title: 'Under 8 Seconds',
    desc: 'Full scan pipeline — upload, extract, detect, preview — completes in under 8 seconds for single-page documents.',
  },
  {
    icon: '🎯',
    title: 'Visual Review',
    desc: 'Color-coded overlays show exactly where PII was found. Toggle individual findings or mask all with one click.',
  },
  {
    icon: '📥',
    title: 'Secure Export',
    desc: 'Download a flattened PDF with irrecoverable redactions — no hidden text layers, no selectable content beneath black bars.',
  },
]

const STEPS = [
  { num: '01', title: 'Upload', desc: 'Drag & drop a PDF or image file' },
  { num: '02', title: 'Scan', desc: 'AI-free regex engine detects Indian PII' },
  { num: '03', title: 'Review', desc: 'Visual overlays highlight every finding' },
  { num: '04', title: 'Redact', desc: 'Mask all or toggle individual items' },
  { num: '05', title: 'Export', desc: 'Download your safe, flattened PDF' },
]

const PII_TYPES = [
  { label: 'Aadhaar', pattern: 'XXXX XXXX 3456', severity: 'high' },
  { label: 'PAN', pattern: 'ABCDE1234F', severity: 'high' },
  { label: 'Phone', pattern: '+91 98765XXXXX', severity: 'medium' },
  { label: 'Email', pattern: 'u***@example.com', severity: 'medium' },
]

export default function Landing() {
  return (
    <div className="landing">
      {/* ─── Hero Section ─── */}
      <section className="hero">
        <div className="hero-badge">
          <span className="hero-badge-dot" />
          Privacy-first · Offline-first · India-focused
        </div>
        <h1 className="hero-title">
          Detect & Redact PII
          <br />
          <span className="hero-gradient">Before It Leaks</span>
        </h1>
        <p className="hero-subtitle">
          Scan PDFs and images for Aadhaar numbers, PAN cards, phone numbers, and emails.
          Review findings visually, mask sensitive data, and export a securely redacted copy
          — all without your document ever leaving your machine.
        </p>
        <div className="hero-actions">
          <SignedIn>
            <Link to="/dashboard" className="primary-button hero-cta">
              Open Scanner →
            </Link>
          </SignedIn>
          <SignedOut>
            <Link to="/sign-in" className="primary-button hero-cta">
              Get Started — Free
            </Link>
            <Link to="/sign-up" className="secondary-button hero-cta">
              Create Account
            </Link>
          </SignedOut>
        </div>

        {/* Floating PII type chips */}
        <div className="hero-chips">
          {PII_TYPES.map((pii) => (
            <div key={pii.label} className={`hero-chip is-${pii.severity}`}>
              <span className="hero-chip-label">{pii.label}</span>
              <code className="hero-chip-pattern">{pii.pattern}</code>
            </div>
          ))}
        </div>
      </section>

      {/* ─── How It Works ─── */}
      <section className="section-block">
        <p className="eyebrow" style={{ textAlign: 'center' }}>How it works</p>
        <h2 className="section-title">Five Steps to a Safe Document</h2>
        <div className="steps-rail">
          {STEPS.map((step, i) => (
            <div key={step.num} className="step-card">
              <span className="step-num">{step.num}</span>
              <h3 className="step-title">{step.title}</h3>
              <p className="step-desc">{step.desc}</p>
              {i < STEPS.length - 1 && <span className="step-arrow">→</span>}
            </div>
          ))}
        </div>
      </section>

      {/* ─── Features Grid ─── */}
      <section className="section-block">
        <p className="eyebrow" style={{ textAlign: 'center' }}>Capabilities</p>
        <h2 className="section-title">Built for Real-World Documents</h2>
        <div className="features-grid">
          {FEATURES.map((f) => (
            <div key={f.title} className="feature-card">
              <span className="feature-icon">{f.icon}</span>
              <h3>{f.title}</h3>
              <p>{f.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ─── Compliance Banner ─── */}
      <section className="section-block">
        <div className="compliance-card">
          <div className="compliance-icon">🏛️</div>
          <div>
            <h3>DPDPA 2023 Ready</h3>
            <p>
              India's Digital Personal Data Protection Act imposes strict obligations
              on data fiduciaries. PII Shield helps small businesses, legal firms, and
              HR departments reduce compliance burden without dedicated privacy teams
              or expensive enterprise software.
            </p>
          </div>
        </div>
      </section>

      {/* ─── CTA Section ─── */}
      <section className="cta-section">
        <h2>Ready to Protect Your Documents?</h2>
        <p>Start scanning in seconds. No setup, no cloud, no data retention.</p>
        <SignedIn>
          <Link to="/dashboard" className="primary-button hero-cta">
            Open Scanner →
          </Link>
        </SignedIn>
        <SignedOut>
          <Link to="/sign-in" className="primary-button hero-cta">
            Sign In to Start
          </Link>
        </SignedOut>
      </section>

      {/* ─── Footer ─── */}
      <footer className="landing-footer">
        <p>
          PII Shield · Built for India · Zero data retention
        </p>
      </footer>
    </div>
  )
}
