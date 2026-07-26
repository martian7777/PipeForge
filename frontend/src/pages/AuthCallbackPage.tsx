import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../auth";

/**
 * Landing page for the OAuth redirect.
 *
 * The backend has already verified the provider's response and set the HttpOnly refresh
 * cookie -- deliberately, no tokens travel in the URL, so nothing lands in browser
 * history or a referrer header. All this page does is trade that cookie for an access
 * token and continue to wherever the user was headed.
 */
export default function AuthCallbackPage() {
  const { adoptSession } = useAuth();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [failed, setFailed] = useState(false);
  const ran = useRef(false); // StrictMode double-invokes effects in development

  useEffect(() => {
    if (ran.current) return;
    ran.current = true;

    const next = params.get("next") || "/";
    adoptSession().then((ok) => {
      if (ok) navigate(next.startsWith("/") ? next : "/", { replace: true });
      else setFailed(true);
    });
  }, [adoptSession, navigate, params]);

  if (failed) {
    return (
      <div style={{ maxWidth: 400, margin: "60px auto" }} className="card">
        <h1>Sign-in failed</h1>
        <p className="subtle">The sign-in session could not be completed.</p>
        <button className="btn" onClick={() => navigate("/login", { replace: true })}>
          Back to sign in
        </button>
      </div>
    );
  }

  return <div className="container spinner">Completing sign-in…</div>;
}
