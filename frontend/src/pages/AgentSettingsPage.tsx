// Per-agent model configuration. Each agent can override the system-default provider
// and model (from GET /api/agents/config), be toggled off, or capped at a step budget.
// Saved via PUT /api/agents/config; changes take effect on the next run.
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { AgentConfig, AgentConfigItem } from "../types";

export default function AgentSettingsPage() {
  const [config, setConfig] = useState<AgentConfig | null>(null);
  const [agents, setAgents] = useState<AgentConfigItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .getAgentConfig()
      .then((c) => {
        setConfig(c);
        setAgents(c.agents);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  const update = (i: number, patch: Partial<AgentConfigItem>) => {
    setSaved(false);
    setAgents((prev) => prev.map((a, idx) => (idx === i ? { ...a, ...patch } : a)));
  };

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      const c = await api.updateAgentConfig(agents);
      setConfig(c);
      setAgents(c.agents);
      setSaved(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  if (error && !config) return <div className="card error">{error}</div>;
  if (!config) return <div className="card spinner">Loading settings…</div>;

  const providers = Object.keys(config.available_models);

  return (
    <div>
      <div className="card">
        <h1>Agent model settings</h1>
        <p className="subtle">
          Active provider: <b>{config.provider}</b>{" "}
          {config.enabled ? (
            <span className="badge boolean">enabled</span>
          ) : (
            <span className="badge">disabled</span>
          )}
        </p>
        {!config.enabled && (
          <p className="subtle">
            The agent layer is off. Set <code>PIPEFORGE_LLM_PROVIDER</code> (and{" "}
            <code>PIPEFORGE_LLM_API_KEY</code>) on the backend to enable it. Per-agent
            overrides below still save.
          </p>
        )}
        <Link className="btn ghost" to="/">
          ← Back
        </Link>
      </div>

      <div className="card">
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Agent</th>
                <th>Enabled</th>
                <th>Provider</th>
                <th>Model</th>
                <th>Max steps</th>
              </tr>
            </thead>
            <tbody>
              {agents.map((a, i) => {
                const models =
                  config.available_models[a.provider ?? config.provider] ?? [];
                return (
                  <tr key={a.agent_name}>
                    <td>{a.label ?? a.agent_name}</td>
                    <td>
                      <input
                        type="checkbox"
                        checked={a.enabled}
                        onChange={(e) => update(i, { enabled: e.target.checked })}
                      />
                    </td>
                    <td>
                      <select
                        value={a.provider ?? ""}
                        onChange={(e) =>
                          update(i, { provider: e.target.value || null, model: null })
                        }
                      >
                        <option value="">(default)</option>
                        {providers.map((p) => (
                          <option key={p} value={p}>
                            {config.provider_labels[p] ?? p}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td>
                      {/* Free-text: any model your provider serves works; the list only suggests. */}
                      <input
                        list={`models-${a.agent_name}`}
                        style={{ width: 170 }}
                        placeholder="(default)"
                        value={a.model ?? ""}
                        onChange={(e) => update(i, { model: e.target.value || null })}
                      />
                      <datalist id={`models-${a.agent_name}`}>
                        {models.map((m) => (
                          <option key={m} value={m} />
                        ))}
                      </datalist>
                    </td>
                    <td>
                      <input
                        type="number"
                        min={1}
                        max={100}
                        style={{ width: 70 }}
                        value={a.max_steps ?? ""}
                        placeholder="—"
                        onChange={(e) =>
                          update(i, {
                            max_steps: e.target.value ? Number(e.target.value) : null,
                          })
                        }
                      />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <div style={{ display: "flex", gap: 10, marginTop: 14, alignItems: "center" }}>
          <button className="btn" onClick={save} disabled={busy}>
            {busy ? "Saving…" : "Save"}
          </button>
          {saved && <span className="subtle">Saved ✓</span>}
          {error && <span className="error">{error}</span>}
        </div>
      </div>
    </div>
  );
}
