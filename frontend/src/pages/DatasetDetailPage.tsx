import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { CleaningConfig, DetectResult, Preview } from "../types";

const TASK_LABELS: Record<string, string> = {
  regression: "Regression",
  classification: "Classification",
  timeseries: "Time series",
  clustering: "Clustering",
};

const DEFAULT_CLEANING: CleaningConfig = {
  drop_duplicates: true,
  impute_numeric: "median",
  impute_categorical: "mode",
  drop_constant_columns: true,
  outlier_method: "none",
};

export default function DatasetDetailPage() {
  const { id } = useParams();
  const datasetId = Number(id);
  const navigate = useNavigate();
  const [preview, setPreview] = useState<Preview | null>(null);
  const [detect, setDetect] = useState<DetectResult | null>(null);
  const [task, setTask] = useState<string>("");
  const [target, setTarget] = useState<string>("");
  const [cleaning, setCleaning] = useState<CleaningConfig>(DEFAULT_CLEANING);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runPipeline = async () => {
    setError(null);
    setRunning(true);
    try {
      const run = await api.createRun({
        dataset_id: datasetId,
        task_type: task,
        target_col: task === "clustering" ? null : target,
        cleaning,
      });
      navigate(`/runs/${run.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setRunning(false);
    }
  };

  useEffect(() => {
    let cancelled = false;
    setError(null);
    Promise.all([api.previewDataset(datasetId), api.detectTask(datasetId)])
      .then(([p, d]) => {
        if (cancelled) return;
        setPreview(p);
        setDetect(d);
        setTask(d.suggested_task);
        setTarget(d.candidate_targets[0]?.column ?? "");
      })
      .catch((e) => !cancelled && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      cancelled = true;
    };
  }, [datasetId]);

  if (error) return <div className="card error">{error}</div>;
  if (!preview || !detect) return <div className="card spinner">Loading dataset…</div>;

  return (
    <div>
      <div className="card">
        <h1>Configure pipeline</h1>
        <div style={{ margin: "10px 0" }}>
          <span className="stat">
            <b>{preview.n_rows.toLocaleString()}</b> rows
          </span>
          <span className="stat">
            <b>{preview.n_cols}</b> columns
          </span>
          {detect.datetime_columns.length > 0 && (
            <span className="stat">
              <b>{detect.datetime_columns.length}</b> datetime column(s)
            </span>
          )}
        </div>

        <div style={{ display: "flex", gap: 24, flexWrap: "wrap", marginTop: 8 }}>
          <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <span className="subtle">Problem type</span>
            <select value={task} onChange={(e) => setTask(e.target.value)}>
              {Object.entries(TASK_LABELS).map(([v, label]) => (
                <option key={v} value={v}>
                  {label}
                  {v === detect.suggested_task ? "  (suggested)" : ""}
                </option>
              ))}
            </select>
          </label>

          {task !== "clustering" && (
            <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <span className="subtle">Target column</span>
              <select value={target} onChange={(e) => setTarget(e.target.value)}>
                {preview.columns.map((c) => (
                  <option key={c.name} value={c.name}>
                    {c.name}
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>

        <div style={{ marginTop: 18, display: "flex", gap: 18, flexWrap: "wrap" }}>
          <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <span className="subtle">Numeric imputation</span>
            <select
              value={cleaning.impute_numeric}
              onChange={(e) =>
                setCleaning({ ...cleaning, impute_numeric: e.target.value as CleaningConfig["impute_numeric"] })
              }
            >
              <option value="median">median</option>
              <option value="mean">mean</option>
              <option value="zero">zero</option>
              <option value="drop">drop rows</option>
            </select>
          </label>
          <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <span className="subtle">Outlier handling</span>
            <select
              value={cleaning.outlier_method}
              onChange={(e) =>
                setCleaning({ ...cleaning, outlier_method: e.target.value as CleaningConfig["outlier_method"] })
              }
            >
              <option value="none">none</option>
              <option value="iqr">clip (IQR)</option>
              <option value="zscore">clip (z-score)</option>
            </select>
          </label>
          <label style={{ display: "flex", alignItems: "flex-end", gap: 8 }}>
            <input
              type="checkbox"
              checked={cleaning.drop_duplicates}
              onChange={(e) => setCleaning({ ...cleaning, drop_duplicates: e.target.checked })}
            />
            <span className="subtle">Drop duplicate rows</span>
          </label>
        </div>

        <div style={{ marginTop: 18 }}>
          <button className="btn" onClick={runPipeline} disabled={running}>
            {running ? "Starting…" : "Run pipeline"}
          </button>
          <span className="subtle" style={{ marginLeft: 12 }}>
            Cleans the data, builds EDA, then trains &amp; ranks models (regression/classification).
          </span>
        </div>
      </div>

      <div className="card">
        <h2>Schema</h2>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Column</th>
                <th>Type</th>
                <th>Dtype</th>
                <th>Missing</th>
                <th>Unique</th>
              </tr>
            </thead>
            <tbody>
              {preview.columns.map((c) => (
                <tr key={c.name}>
                  <td>{c.name}</td>
                  <td>
                    <span className={`badge ${c.semantic}`}>{c.semantic}</span>
                  </td>
                  <td className="subtle">{c.dtype}</td>
                  <td>{c.n_missing}</td>
                  <td>{c.n_unique}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card">
        <h2>Preview</h2>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                {preview.columns.map((c) => (
                  <th key={c.name}>{c.name}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {preview.rows.map((row, i) => (
                <tr key={i}>
                  {preview.columns.map((c) => (
                    <td key={c.name}>{formatCell(row[c.name])}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function formatCell(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") return String(v);
  return String(v);
}
