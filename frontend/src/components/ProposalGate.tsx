// Copilot approval gate. Renders the agent's proposed stage config (cleaning or
// modeling) as an editable form; Approve sends any edits back, Reject stops the flow.
import { useState, type ReactNode } from "react";
import type { AgentProposal } from "../types";

export default function ProposalGate({
  proposal,
  busy,
  onApprove,
  onReject,
}: {
  proposal: AgentProposal;
  busy?: boolean;
  onApprove: (edited: Record<string, unknown>) => void;
  onReject: () => void;
}) {
  const [cfg, setCfg] = useState<Record<string, unknown>>({ ...proposal.proposed_config_json });
  const set = (k: string, v: unknown) => setCfg((c) => ({ ...c, [k]: v }));

  return (
    <div className="card" style={{ borderColor: "var(--accent, #2563eb)", borderWidth: 1, borderStyle: "solid" }}>
      <h2>
        Approval needed — <span className="badge">{proposal.stage}</span>
      </h2>
      <p className="subtle">Review the agent's proposed configuration and approve (with edits) or reject.</p>

      {proposal.stage === "cleaning" && (
        <div style={{ display: "grid", gap: 10, maxWidth: 480, marginTop: 12 }}>
          <Row label="Drop duplicates">
            <input type="checkbox" checked={!!cfg.drop_duplicates} onChange={(e) => set("drop_duplicates", e.target.checked)} />
          </Row>
          <Row label="Drop constant columns">
            <input type="checkbox" checked={!!cfg.drop_constant_columns} onChange={(e) => set("drop_constant_columns", e.target.checked)} />
          </Row>
          <Row label="Numeric imputation">
            <Select value={String(cfg.impute_numeric)} opts={["median", "mean", "zero", "drop"]} onChange={(v) => set("impute_numeric", v)} />
          </Row>
          <Row label="Categorical imputation">
            <Select value={String(cfg.impute_categorical)} opts={["mode", "constant", "drop"]} onChange={(v) => set("impute_categorical", v)} />
          </Row>
          <Row label="Outlier method">
            <Select value={String(cfg.outlier_method)} opts={["none", "iqr", "zscore"]} onChange={(v) => set("outlier_method", v)} />
          </Row>
        </div>
      )}

      {proposal.stage === "modeling" && (
        <div style={{ display: "grid", gap: 10, maxWidth: 520, marginTop: 12 }}>
          <div>
            <div className="subtle">Selected models</div>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 6 }}>
              {(cfg.selected_models as string[] | undefined)?.map((m) => (
                <span key={m} className="badge">
                  {m}
                </span>
              )) ?? <span className="subtle">(all)</span>}
            </div>
          </div>
          <Row label="Test split size">
            <input
              type="number"
              min={0.05}
              max={0.5}
              step={0.05}
              style={{ width: 90 }}
              value={Number(cfg.test_size ?? 0.2)}
              onChange={(e) => set("test_size", Number(e.target.value))}
            />
          </Row>
        </div>
      )}

      <div style={{ display: "flex", gap: 10, marginTop: 16 }}>
        <button className="btn" disabled={busy} onClick={() => onApprove(cfg)}>
          {busy ? "Working…" : "Approve"}
        </button>
        <button className="btn secondary" disabled={busy} onClick={onReject}>
          Reject
        </button>
      </div>
    </div>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
      <span>{label}</span>
      {children}
    </label>
  );
}

function Select({ value, opts, onChange }: { value: string; opts: string[]; onChange: (v: string) => void }) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)}>
      {opts.map((o) => (
        <option key={o} value={o}>
          {o}
        </option>
      ))}
    </select>
  );
}
