import { Outlet, Link, useLocation } from 'react-router-dom'
import { SignedIn, SignedOut, UserButton } from '@clerk/clerk-react'

export default function Layout() {
  const location = useLocation()
  const isLanding = location.pathname === '/'
  const isAuth = location.pathname.startsWith('/sign-')

  return (
    <div className="app-shell">
      {/* ─── Navigation Bar ─── */}
      <header className={`navbar ${isLanding ? 'navbar-landing' : ''}`}>
        <Link to="/" className="navbar-brand">
          <span className="navbar-logo">🛡️</span>
          <span className="navbar-wordmark">PII Shield</span>
        </Link>

        <nav className="navbar-links">
          <SignedIn>
            <Link
              to="/dashboard"
              className={`navbar-link ${location.pathname === '/dashboard' ? 'is-active' : ''}`}
            >
              Scanner
            </Link>
            <UserButton
              afterSignOutUrl="/"
              appearance={{
                elements: {
                  avatarBox: { width: '36px', height: '36px' },
                },
              }}
            />
          </SignedIn>

          <SignedOut>
            <Link to="/sign-in" className="navbar-link">
              Sign In
            </Link>
            <Link to="/sign-up" className="primary-button navbar-signup">
              Get Started
            </Link>
          </SignedOut>
        </nav>
      </header>

      {/* ─── Page Content ─── */}
      <main className={isAuth ? 'auth-main' : ''}>
        <Outlet />
      </main>
    </div>
  )
}
