import { lazy, Suspense, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api/client";
import type { EdaResult } from "../types";

// Plotly is heavy (~1.5MB gzip); load it only when the EDA dashboard renders.
const Chart = lazy(() => import("../components/Chart"));

function StatTile({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="stat" style={{ display: "block" }}>
      <div className="subtle">{label}</div>
      <b style={{ fontSize: 22 }}>{value}</b>
    </div>
  );
}

export default function RunEdaPage() {
  const { id } = useParams();
  const runId = Number(id);
  const [eda, setEda] = useState<EdaResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .getEda(runId)
      .then((r) => !cancelled && setEda(r))
      .catch((e) => !cancelled && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      cancelled = true;
    };
  }, [runId]);

  if (error) return <div className="card error">{error}</div>;
  if (!eda) return <div className="card spinner">Running pipeline &amp; building EDA…</div>;

  const s = eda.summary as Record<string, number>;

  return (
    <div>
      <div className="card">
        <h1>EDA dashboard</h1>
        <div style={{ display: "flex", gap: 14, flexWrap: "wrap", marginTop: 12 }}>
          <StatTile label="Rows" value={(s.n_rows ?? 0).toLocaleString()} />
          <StatTile label="Columns" value={s.n_cols ?? 0} />
          <StatTile label="Numeric" value={s.n_numeric ?? 0} />
          <StatTile label="Categorical" value={s.n_categorical ?? 0} />
          <StatTile label="Datetime" value={s.n_datetime ?? 0} />
          <StatTile label="Missing cells" value={(s.total_missing ?? 0).toLocaleString()} />
        </div>
        {eda.report_url && (
          <div style={{ marginTop: 16 }}>
            <a className="btn secondary" href={`/api/runs/${runId}/report`} target="_blank" rel="noreferrer">
              Open full HTML report ↗
            </a>
          </div>
        )}
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(360px, 1fr))",
          gap: 4,
        }}
      >
        <Suspense fallback={<div className="card spinner">Loading charts…</div>}>
          {eda.charts.map((c) => (
            <Chart key={c.id} spec={c} />
          ))}
        </Suspense>
      </div>
    </div>
  );
}
