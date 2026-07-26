import { Link, Outlet } from "react-router-dom";
import { useAuth } from "./auth";

export default function App() {
  const { user, isAdmin, logout } = useAuth();
  return (
    <div>
      <header className="app-header">
        <Link to="/" className="logo">
          Pipe<span>Forge</span>
        </Link>
        <span className="tag">End-to-end data science pipeline platform</span>
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 12 }}>
          {user && (
            <span className="subtle" title={`Role: ${user.role}`}>
              {user.email}
              {isAdmin && " · admin"}
            </span>
          )}
          {user && (
            <Link className="btn ghost" to="/settings/agents">
              Agents
            </Link>
          )}
          {isAdmin && (
            <Link className="btn ghost" to="/admin">
              Admin
            </Link>
          )}
          {user && (
            <button className="btn ghost" onClick={() => void logout()}>
              Sign out
            </button>
          )}
        </div>
      </header>
      <main className="container">
        <Outlet />
      </main>
    </div>
  );
}
