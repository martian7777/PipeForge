// Reasoning + chat transcript for an agent session. Renders assistant/user messages
// (tool calls are shown on AgentBoard); for chat mode it also renders a composer.
import { useState } from "react";
import type { AgentMessage, AgentSessionDetail } from "../types";

function Bubble({ m }: { m: AgentMessage }) {
  const isUser = m.role === "user";
  const isError = m.role === "error";
  return (
    <div
      style={{
        display: "flex",
        justifyContent: isUser ? "flex-end" : "flex-start",
        marginTop: 10,
      }}
    >
      <div
        className={isError ? "error" : undefined}
        style={{
          maxWidth: "80%",
          background: isUser ? "var(--accent, #2563eb)" : "var(--panel-2, #1c2230)",
          color: isUser ? "#fff" : undefined,
          borderRadius: 12,
          padding: "10px 12px",
          whiteSpace: "pre-wrap",
          lineHeight: 1.5,
        }}
      >
        {!isUser && !isError && m.agent_name && (
          <div className="subtle" style={{ fontSize: 11, marginBottom: 4 }}>
            {m.agent_name}
          </div>
        )}
        {m.content}
      </div>
    </div>
  );
}

export default function AgentPanel({
  session,
  onSend,
  busy,
}: {
  session: AgentSessionDetail;
  onSend?: (text: string) => void;
  busy?: boolean;
}) {
  const [text, setText] = useState("");
  const visible = session.messages.filter(
    (m) => (m.role === "user" || m.role === "assistant" || m.role === "error") && m.content
  );

  const submit = () => {
    const t = text.trim();
    if (!t || !onSend || busy) return;
    onSend(t);
    setText("");
  };

  return (
    <div className="card">
      <h2>{onSend ? "Ask the Analyst" : "Analysis"}</h2>
      <div>
        {visible.length === 0 && !busy && (
          <p className="subtle">No messages yet.</p>
        )}
        {visible.map((m) => (
          <Bubble key={m.id} m={m} />
        ))}
        {busy && <div className="spinner" style={{ marginTop: 10 }}>Agent is working…</div>}
      </div>

      {onSend && (
        <div style={{ display: "flex", gap: 8, marginTop: 14 }}>
          <input
            style={{ flex: 1 }}
            placeholder="Ask about this dataset or its results…"
            value={text}
            disabled={busy}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") submit();
            }}
          />
          <button className="btn" disabled={busy || !text.trim()} onClick={submit}>
            Send
          </button>
        </div>
      )}
    </div>
  );
}
