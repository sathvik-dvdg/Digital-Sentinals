import { SignIn } from '@clerk/clerk-react'

export default function Login() {
  return (
    <div className="auth-page">
      <SignIn routing="path" path="/sign-in" signUpUrl="/sign-up" />
    </div>
  )
}
