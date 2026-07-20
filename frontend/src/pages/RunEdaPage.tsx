import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { api, tokenStore } from "../api/client";
import type { EdaResult, Leaderboard, ModelDetail, RunStatus } from "../types";

const Chart = lazy(() => import("../components/Chart"));
const EvalCharts = lazy(() => import("../components/EvalCharts"));

function StatTile({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="stat" style={{ display: "block" }}>
      <div className="subtle">{label}</div>
      <b style={{ fontSize: 22 }}>{value}</b>
    </div>
  );
}

function ProgressView({ status }: { status: RunStatus }) {
  return (
    <div className="card">
      <h1>Running pipeline…</h1>
      <p className="subtle">
        Stage: <b>{status.stage}</b> {status.message ? `· ${status.message}` : ""}
      </p>
      <div style={{ background: "var(--panel-2)", borderRadius: 999, height: 12, overflow: "hidden", marginTop: 12 }}>
        <div
          style={{
            width: `${status.progress}%`,
            height: "100%",
            background: "linear-gradient(90deg, var(--accent), var(--accent-2))",
            transition: "width 0.4s ease",
          }}
        />
      </div>
      <div className="subtle" style={{ marginTop: 6 }}>{Math.round(status.progress)}%</div>
    </div>
  );
}

function fmtMetric(v: number | undefined): string {
  if (v === undefined || v === null) return "—";
  return Math.abs(v) >= 1000 || Math.abs(v) < 0.001 ? v.toExponential(3) : v.toFixed(4);
}

export default function RunEdaPage() {
  const { id } = useParams();
  const runId = Number(id);
  const [status, setStatus] = useState<RunStatus | null>(null);
  const [eda, setEda] = useState<EdaResult | null>(null);
  const [lb, setLb] = useState<Leaderboard | null>(null);
  const [detail, setDetail] = useState<ModelDetail | null>(null);
  const [tab, setTab] = useState<"leaderboard" | "eda">("leaderboard");
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<number | null>(null);

  // Poll status until the run finishes.
  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      try {
        const s = await api.getRunStatus(runId);
        if (cancelled) return;
        setStatus(s);
        if (s.status === "done" || s.status === "error") {
          if (timer.current) window.clearInterval(timer.current);
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
        if (timer.current) window.clearInterval(timer.current);
      }
    };
    void tick();
    timer.current = window.setInterval(tick, 1500);
    return () => {
      cancelled = true;
      if (timer.current) window.clearInterval(timer.current);
    };
  }, [runId]);

  const selectModel = useCallback(
    async (modelId: number) => {
      setDetail(null);
      try {
        setDetail(await api.getModelDetail(runId, modelId));
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    },
    [runId]
  );

  // Once done, load EDA + leaderboard, and select the best model.
  useEffect(() => {
    if (status?.status !== "done") return;
    Promise.all([api.getEda(runId), api.getLeaderboard(runId)])
      .then(([e, l]) => {
        setEda(e);
        setLb(l);
        if (l.best_model_id) void selectModel(l.best_model_id);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [status?.status, runId, selectModel]);

  if (error) return <div className="card error">{error}</div>;
  if (!status) return <div className="card spinner">Loading run…</div>;
  if (status.status === "error")
    return <div className="card error">Run failed: {status.message}</div>;
  if (status.status !== "done") return <ProgressView status={status} />;

  const s = (eda?.summary ?? {}) as Record<string, number>;

  return (
    <div>
      <div className="card">
        <h1>Run #{runId} results</h1>
        <p className="subtle">{status.message}</p>
        <div style={{ display: "flex", gap: 10, marginTop: 12 }}>
          <button
            className={`btn ${tab === "leaderboard" ? "" : "secondary"}`}
            onClick={() => setTab("leaderboard")}
          >
            Leaderboard
          </button>
          <button className={`btn ${tab === "eda" ? "" : "secondary"}`} onClick={() => setTab("eda")}>
            EDA
          </button>
          {eda?.report_url && (
            <a className="btn ghost" href={`/api/runs/${runId}/report?token=${tokenStore.get() || ""}`} target="_blank" rel="noreferrer">
              HTML report ↗
            </a>
          )}
        </div>
      </div>

      {tab === "leaderboard" && (
        <>
          {lb && lb.models.length > 0 ? (
            <>
              <div className="card">
                <h2>Model leaderboard {lb.primary_metric && `(ranked by ${lb.primary_metric})`}</h2>
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>#</th>
                        <th>Model</th>
                        <th>Family</th>
                        {Object.keys(lb.models[0].metrics_json).map((k) => (
                          <th key={k}>{k}</th>
                        ))}
                        <th></th>
                      </tr>
                    </thead>
                    <tbody>
                      {lb.models.map((m) => (
                        <tr
                          key={m.id}
                          onClick={() => selectModel(m.id)}
                          style={{
                            cursor: "pointer",
                            background: detail?.id === m.id ? "var(--panel-2)" : undefined,
                          }}
                        >
                          <td>{m.rank === 999 ? "—" : m.rank}</td>
                          <td>
                            {m.model_name}{" "}
                            {m.id === lb.best_model_id && <span className="badge boolean">best</span>}
                          </td>
                          <td>
                            <span className="badge">{m.family}</span>
                          </td>
                          {Object.keys(lb.models[0].metrics_json).map((k) => (
                            <td key={k}>{fmtMetric(m.metrics_json[k])}</td>
                          ))}
                          <td>
                            {m.has_artifact && (
                              <button
                                className="btn ghost"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  void api.downloadModel(runId, m.id, `${m.model_name.replace(/ /g, "_")}.joblib`);
                                }}
                              >
                                Download
                              </button>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {detail && (
                <div className="card">
                  <h2>{detail.model_name} — evaluation</h2>
                  <Suspense fallback={<div className="spinner">Loading charts…</div>}>
                    <EvalCharts plots={detail.plots_json} />
                  </Suspense>
                </div>
              )}

              {lb.best_model_id && <PredictWidget runId={runId} />}
            </>
          ) : (
            <div className="card subtle">
              No models were trained for this run (only supervised regression/classification
              tasks train models in this milestone).
            </div>
          )}
        </>
      )}

      {tab === "eda" && eda && (
        <>
          <div className="card">
            <h2>Dataset overview</h2>
            <div style={{ display: "flex", gap: 14, flexWrap: "wrap", marginTop: 12 }}>
              <StatTile label="Rows" value={(s.n_rows ?? 0).toLocaleString()} />
              <StatTile label="Columns" value={s.n_cols ?? 0} />
              <StatTile label="Numeric" value={s.n_numeric ?? 0} />
              <StatTile label="Categorical" value={s.n_categorical ?? 0} />
              <StatTile label="Datetime" value={s.n_datetime ?? 0} />
              <StatTile label="Missing cells" value={(s.total_missing ?? 0).toLocaleString()} />
            </div>
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
        </>
      )}
    </div>
  );
}

function PredictWidget({ runId }: { runId: number }) {
  const [preds, setPreds] = useState<unknown[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const onFile = async (file: File) => {
    setError(null);
    setBusy(true);
    setPreds(null);
    try {
      const r = await api.predict(runId, file);
      setPreds(r.predictions);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card">
      <h2>Predict on new data</h2>
      <p className="subtle">
        Upload a file with the same feature columns (no target needed). The best model
        returns a prediction per row.
      </p>
      <input
        type="file"
        accept=".csv,.tsv,.json,.xlsx,.xls,.parquet"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) void onFile(f);
        }}
      />
      {busy && <div className="spinner" style={{ marginTop: 10 }}>Predicting…</div>}
      {error && <div className="error">{error}</div>}
      {preds && (
        <div style={{ marginTop: 12 }}>
          <div className="subtle">{preds.length} prediction(s):</div>
          <div className="table-scroll" style={{ marginTop: 6, maxHeight: 240 }}>
            <table>
              <thead>
                <tr>
                  <th>Row</th>
                  <th>Prediction</th>
                </tr>
              </thead>
              <tbody>
                {preds.slice(0, 100).map((p, i) => (
                  <tr key={i}>
                    <td>{i + 1}</td>
                    <td>{typeof p === "number" ? p.toFixed(4) : String(p)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
