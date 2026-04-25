import { SignUp } from '@clerk/clerk-react'

export default function Signup() {
  return (
    <div className="auth-page">
      <SignUp routing="path" path="/sign-up" signInUrl="/sign-in" />
    </div>
  )
}
