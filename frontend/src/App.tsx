import { Link, Outlet } from "react-router-dom";
import { useAuth } from "./auth";

export default function App() {
  const { user, logout } = useAuth();
  return (
    <div>
      <header className="app-header">
        <Link to="/" className="logo">
          Auto<span>DS</span>
        </Link>
        <span className="tag">End-to-end data science pipeline platform</span>
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 12 }}>
          {user && <span className="subtle">{user.email}</span>}
          {user && (
            <button className="btn ghost" onClick={logout}>
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
