// Live "who's working" board. One card per agent involved in the session, with a
// status badge (idle → working → done → error) and the tools it called. Status is
// derived from the session's message trace + current_agent, so it reflects the live DB.
import type { AgentSessionDetail } from "../types";

type AgentStatus = "idle" | "working" | "done" | "error";

const AGENT_LABELS: Record<string, string> = {
  orchestrator: "Forge Master",
  profiler: "Profiler",
  cleaning: "Cleaning Agent",
  eda_analyst: "EDA Analyst",
  modeling: "Modeling Strategist",
  critic: "Evaluation Critic",
  chat: "Data Analyst",
};

const STATUS_STYLE: Record<AgentStatus, { badge: string; dot: string }> = {
  idle: { badge: "badge", dot: "var(--muted, #888)" },
  working: { badge: "badge", dot: "var(--accent, #3b82f6)" },
  done: { badge: "badge boolean", dot: "#22c55e" },
  error: { badge: "badge error", dot: "#ef4444" },
};

function statusFor(session: AgentSessionDetail, name: string): AgentStatus {
  if (session.error_json && (session.error_json as { agent?: string }).agent === name) return "error";
  if (session.messages.some((m) => m.role === "error" && m.agent_name === name)) return "error";
  if (session.status === "running" && session.current_agent === name) return "working";
  if (session.messages.some((m) => m.agent_name === name && (m.role === "assistant" || m.role === "tool")))
    return "done";
  return "idle";
}

export default function AgentBoard({ session }: { session: AgentSessionDetail }) {
  const names = Array.from(
    new Set(
      [
        session.current_agent,
        ...session.messages.map((m) => m.agent_name),
      ].filter((n): n is string => !!n)
    )
  );
  if (names.length === 0) return null;

  return (
    <div className="card">
      <h2>Agents</h2>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))",
          gap: 10,
          marginTop: 10,
        }}
      >
        {names.map((name) => {
          const st = statusFor(session, name);
          const style = STATUS_STYLE[st];
          const tools = session.messages
            .filter((m) => m.agent_name === name && m.role === "tool" && m.tool_name)
            .map((m) => m.tool_name as string);
          const err = session.messages.find((m) => m.agent_name === name && m.role === "error");
          return (
            <div key={name} className="stat" style={{ display: "block" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span
                  style={{
                    width: 8,
                    height: 8,
                    borderRadius: 999,
                    background: style.dot,
                    boxShadow: st === "working" ? `0 0 6px ${style.dot}` : "none",
                  }}
                />
                <b>{AGENT_LABELS[name] ?? name}</b>
                <span className={style.badge} style={{ marginLeft: "auto" }}>
                  {st}
                </span>
              </div>
              {tools.length > 0 && (
                <div className="subtle" style={{ marginTop: 6, fontSize: 12 }}>
                  {tools.join(" · ")}
                </div>
              )}
              {err?.content && (
                <div className="error" style={{ marginTop: 6, fontSize: 12 }}>
                  {err.content}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
