import './App.css'
import { Show, SignInButton, SignUpButton, UserButton } from '@clerk/react'

function App() {
  return (
    <>
      <nav style={{ display: 'flex', justifyContent: 'space-between', padding: '20px 40px', borderBottom: '1px solid var(--border)' }}>
        <div className="logo" style={{ fontWeight: 'bold', fontSize: '20px', color: 'var(--text-h)' }}>PROTOTYPE</div>
        <div className="auth-tokens" style={{ display: 'flex', gap: '15px' }}>
          <Show when="signed-out">
            <SignInButton mode="modal">
              <button className="counter">Log In</button>
            </SignInButton>
            <SignUpButton mode="modal">
              <button className="counter" style={{ background: 'var(--accent)', color: 'white' }}>Sign Up</button>
            </SignUpButton>
          </Show>
          <Show when="signed-in">
            <UserButton />
          </Show>
        </div>
      </nav>

      <main id="center">
        <section className="hero">
          <h1>Build the Future Fast.</h1>
          <p style={{ maxWidth: '600px', margin: '0 auto 32px' }}>
            Experience the power of our hackathon prototype. Secure, scalable, and ready for deployment.
          </p>
          <div className="hero-visual">
            <img src="/src/assets/hero.png" className="base" alt="Hero Base" />
            {/* These utilize your existing .framework and .vite CSS classes */}
            <img src="/src/assets/react.svg" className="framework" alt="React" />
            <img src="/src/assets/vite.svg" className="vite" alt="Vite" />
          </div>
        </section>

        <section id="next-steps">
          <div id="docs">
            <h2>Fast Integration</h2>
            <p>Connect your tools in minutes using our optimized API layers.</p>
          </div>
          <div>
            <h2>Clerk Security</h2>
            <p>Enterprise-grade authentication handled right out of the box.</p>
          </div>
        </section>
      </main>

      <footer id="spacer" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <p>© 2025 Hackathon Project. Powered by Vite + Clerk.</p>
      </footer>
    </>
  )
}

export default App