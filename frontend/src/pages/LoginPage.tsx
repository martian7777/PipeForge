import { useEffect, useState } from "react";
import { Navigate, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../auth";
import type { SsoProvider } from "../types";

/** Brand marks are inline SVG so the page pulls nothing from a third-party CDN. */
const PROVIDER_ICON: Record<string, JSX.Element> = {
  google: (
    <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true">
      <path fill="#4285F4" d="M23 12.3c0-.8-.1-1.6-.2-2.3H12v4.5h6.2a5.3 5.3 0 0 1-2.3 3.5v2.9h3.7c2.2-2 3.4-5 3.4-8.6z" />
      <path fill="#34A853" d="M12 24c3.1 0 5.7-1 7.6-2.8l-3.7-2.9c-1 .7-2.3 1.1-3.9 1.1-3 0-5.5-2-6.4-4.7H1.8v3C3.7 21.4 7.6 24 12 24z" />
      <path fill="#FBBC05" d="M5.6 14.7a7.2 7.2 0 0 1 0-4.6v-3H1.8a12 12 0 0 0 0 10.6l3.8-3z" />
      <path fill="#EA4335" d="M12 4.8c1.7 0 3.2.6 4.4 1.7l3.2-3.2C17.7 1.5 15.1.4 12 .4 7.6.4 3.7 3 1.8 6.8l3.8 3C6.5 7.1 9 4.8 12 4.8z" />
    </svg>
  ),
  github: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
      <path d="M8 0C3.6 0 0 3.6 0 8a8 8 0 0 0 5.5 7.6c.4 0 .5-.2.5-.4v-1.4c-2.2.5-2.7-1-2.7-1-.4-1-.9-1.2-.9-1.2-.7-.5.1-.5.1-.5.8.1 1.2.8 1.2.8.7 1.2 1.9.9 2.4.7 0-.6.3-.9.5-1.1-1.8-.2-3.6-.9-3.6-4 0-.9.3-1.6.8-2.1 0-.2-.3-1 .1-2.1 0 0 .7-.2 2.2.8a7.6 7.6 0 0 1 4 0c1.5-1 2.2-.8 2.2-.8.4 1.1.2 1.9.1 2.1.5.5.8 1.2.8 2.1 0 3.1-1.9 3.7-3.7 3.9.3.3.6.8.6 1.6v2.2c0 .2.1.5.6.4A8 8 0 0 0 16 8c0-4.4-3.6-8-8-8z" />
    </svg>
  ),
  microsoft: (
    <svg width="16" height="16" viewBox="0 0 23 23" aria-hidden="true">
      <path fill="#F25022" d="M1 1h10v10H1z" />
      <path fill="#7FBA00" d="M12 1h10v10H12z" />
      <path fill="#00A4EF" d="M1 12h10v10H1z" />
      <path fill="#FFB900" d="M12 12h10v10H12z" />
    </svg>
  ),
};

export default function LoginPage() {
  const { login, register, loginWithSso, user } = useAuth();
  const [params] = useSearchParams();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [providers, setProviders] = useState<SsoProvider[]>([]);
  const [error, setError] = useState<string | null>(params.get("sso_error"));
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .authOptions()
      .then((opts) => setProviders(opts.providers))
      .catch(() => setProviders([]));
  }, []);

  if (user) return <Navigate to="/" replace />;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (mode === "login") await login(email, password);
      else await register(email, password);
      // AuthProvider updates user; router redirects.
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ maxWidth: 400, margin: "60px auto" }}>
      <div className="card">
        <h1>{mode === "login" ? "Sign in" : "Create account"}</h1>
        <p className="subtle">Access your PipeForge workspace.</p>

        {providers.length > 0 && (
          <>
            <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 16 }}>
              {providers.map((p) => (
                <button
                  key={p.name}
                  type="button"
                  className="btn ghost"
                  onClick={() => loginWithSso(p.name)}
                  style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 8 }}
                >
                  {PROVIDER_ICON[p.name]}
                  Continue with {p.label}
                </button>
              ))}
            </div>
            <div
              className="subtle"
              style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}
            >
              <hr style={{ flex: 1, border: 0, borderTop: "1px solid var(--border, #333)" }} />
              or
              <hr style={{ flex: 1, border: 0, borderTop: "1px solid var(--border, #333)" }} />
            </div>
          </>
        )}

        <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <span className="subtle">Email</span>
            <input
              type="email"
              value={email}
              required
              autoComplete="username"
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
            />
          </label>
          <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <span className="subtle">Password (min 12 chars)</span>
            <input
              type="password"
              value={password}
              required
              minLength={12}
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••••••"
            />
          </label>
          <button className="btn" type="submit" disabled={busy}>
            {busy ? "Please wait…" : mode === "login" ? "Sign in" : "Register"}
          </button>
        </form>
        {error && <div className="error">{error}</div>}
        <div style={{ marginTop: 14 }} className="subtle">
          {mode === "login" ? "No account?" : "Already registered?"}{" "}
          <a
            href="#"
            onClick={(e) => {
              e.preventDefault();
              setError(null);
              setMode(mode === "login" ? "register" : "login");
            }}
          >
            {mode === "login" ? "Create one" : "Sign in"}
          </a>
        </div>
      </div>
    </div>
  );
}
