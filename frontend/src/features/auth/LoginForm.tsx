import { FormEvent, useState } from "react";

interface LoginFormProps {
  onSubmit: (password: string) => Promise<void> | void;
  isSubmitting: boolean;
  error: string | null;
}

export function LoginForm({ onSubmit, isSubmitting, error }: LoginFormProps) {
  const [password, setPassword] = useState("");

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await onSubmit(password);
  }

  return (
    <div className="panel auth-panel">
      <h2>Login</h2>
      <p>Use the existing Flask session auth so the new frontend can access the API safely.</p>
      <form onSubmit={handleSubmit} className="stack">
        <label className="field">
          <span>Password</span>
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            placeholder="Enter project password"
            autoComplete="current-password"
            required
          />
        </label>
        {error ? <p className="error-banner">{error}</p> : null}
        <button type="submit" className="primary-button" disabled={isSubmitting}>
          {isSubmitting ? "Signing in..." : "Sign in"}
        </button>
      </form>
    </div>
  );
}
