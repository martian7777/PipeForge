import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import { useAuth } from "../auth";
import type { AuditEntry, AuthUser, Role } from "../types";

const ROLES: Role[] = ["viewer", "user", "admin"];

export default function AdminPage() {
  const { user: me } = useAuth();
  const [tab, setTab] = useState<"users" | "audit">("users");
  const [users, setUsers] = useState<AuthUser[]>([]);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [query, setQuery] = useState("");
  const [eventFilter, setEventFilter] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const loadUsers = useCallback(async () => {
    try {
      setUsers(await api.adminListUsers(query || undefined));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [query]);

  const loadAudit = useCallback(async () => {
    try {
      setAudit(await api.adminAuditLog({ event_prefix: eventFilter || undefined, limit: 200 }));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [eventFilter]);

  useEffect(() => {
    if (tab === "users") void loadUsers();
    else void loadAudit();
  }, [tab, loadUsers, loadAudit]);

  const act = async (fn: () => Promise<unknown>) => {
    setError(null);
    setBusy(true);
    try {
      await fn();
      await loadUsers();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <h1>Administration</h1>
      <div style={{ display: "flex", gap: 8, margin: "12px 0 20px" }}>
        <button
          className={tab === "users" ? "btn" : "btn ghost"}
          onClick={() => setTab("users")}
        >
          Users
        </button>
        <button
          className={tab === "audit" ? "btn" : "btn ghost"}
          onClick={() => setTab("audit")}
        >
          Audit log
        </button>
      </div>

      {error && <div className="error">{error}</div>}

      {tab === "users" && (
        <div className="card">
          <input
            placeholder="Filter by email…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            style={{ marginBottom: 12, width: "100%" }}
          />
          <div style={{ overflowX: "auto" }}>
            <table>
              <thead>
                <tr>
                  <th>Email</th>
                  <th>Role</th>
                  <th>Status</th>
                  <th>Last sign-in</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.id} style={{ opacity: u.is_active ? 1 : 0.5 }}>
                    <td>
                      {u.email}
                      {u.id === me?.id && <span className="subtle"> (you)</span>}
                    </td>
                    <td>
                      <select
                        value={u.role}
                        disabled={busy}
                        onChange={(e) => act(() => api.adminSetRole(u.id, e.target.value as Role))}
                      >
                        {ROLES.map((r) => (
                          <option key={r} value={r}>
                            {r}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td>{u.is_active ? "active" : "disabled"}</td>
                    <td className="subtle">
                      {u.last_login_at ? new Date(u.last_login_at).toLocaleString() : "never"}
                    </td>
                    <td style={{ display: "flex", gap: 6 }}>
                      <button
                        className="btn ghost"
                        disabled={busy}
                        onClick={() => act(() => api.adminSetActive(u.id, !u.is_active))}
                      >
                        {u.is_active ? "Disable" : "Enable"}
                      </button>
                      <button
                        className="btn ghost"
                        disabled={busy}
                        title="Force sign-out on every device"
                        onClick={() => act(() => api.adminRevokeSessions(u.id))}
                      >
                        Revoke sessions
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {tab === "audit" && (
        <div className="card">
          <input
            placeholder="Filter by event prefix, e.g. auth. or admin.…"
            value={eventFilter}
            onChange={(e) => setEventFilter(e.target.value)}
            style={{ marginBottom: 12, width: "100%" }}
          />
          <div style={{ overflowX: "auto" }}>
            <table>
              <thead>
                <tr>
                  <th>When</th>
                  <th>Event</th>
                  <th>Actor</th>
                  <th>Target</th>
                  <th>Outcome</th>
                  <th>IP</th>
                  <th>Request</th>
                </tr>
              </thead>
              <tbody>
                {audit.map((entry) => (
                  <tr key={entry.id}>
                    <td className="subtle">{new Date(entry.created_at).toLocaleString()}</td>
                    <td>
                      <code>{entry.event}</code>
                    </td>
                    <td>{entry.actor_email ?? "—"}</td>
                    <td>{entry.target ?? "—"}</td>
                    <td className={entry.outcome === "failure" ? "error" : undefined}>
                      {entry.outcome}
                    </td>
                    <td className="subtle">{entry.client_ip ?? "—"}</td>
                    <td className="subtle" title={entry.request_id ?? ""}>
                      {entry.request_id?.slice(0, 8) ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {audit.length === 0 && <p className="subtle">No matching events.</p>}
        </div>
      )}
    </div>
  );
}
