import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { Dataset } from "../types";

export default function UploadPage() {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();

  const refresh = useCallback(() => {
    api.listDatasets().then(setDatasets).catch((e) => setError(String(e.message ?? e)));
  }, []);

  useEffect(refresh, [refresh]);

  const upload = useCallback(
    async (file: File) => {
      setError(null);
      setUploading(true);
      try {
        const ds = await api.uploadDataset(file);
        navigate(`/datasets/${ds.id}`);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setUploading(false);
      }
    },
    [navigate]
  );

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) void upload(file);
  };

  return (
    <div>
      <div className="card">
        <h1>Upload a dataset</h1>
        <p className="subtle">
          CSV, TSV, JSON, Excel, or Parquet. We'll infer the schema, then you pick the
          problem type and let AutoDS build the pipeline.
        </p>
        <div
          className={`dropzone ${dragging ? "drag" : ""}`}
          onClick={() => inputRef.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
        >
          {uploading ? (
            <div className="spinner">Uploading &amp; parsing…</div>
          ) : (
            <>
              <div style={{ fontSize: 16, fontWeight: 600 }}>
                Drop a file here, or click to browse
              </div>
              <div className="hint">.csv .tsv .json .xlsx .parquet</div>
            </>
          )}
          <input
            ref={inputRef}
            type="file"
            accept=".csv,.tsv,.txt,.json,.xlsx,.xls,.parquet,.pq"
            style={{ display: "none" }}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) void upload(file);
            }}
          />
        </div>
        {error && <div className="error">{error}</div>}
      </div>

      <div className="card">
        <h2>Your datasets</h2>
        {datasets.length === 0 ? (
          <p className="subtle">No datasets yet — upload one above.</p>
        ) : (
          <div className="dataset-list">
            {datasets.map((d) => (
              <div key={d.id} className="dataset-row">
                <div>
                  <a href={`/datasets/${d.id}`}>{d.filename}</a>
                  <div className="meta">
                    {d.n_rows.toLocaleString()} rows × {d.n_cols} cols · {d.file_format}
                  </div>
                </div>
                <button
                  className="btn ghost"
                  onClick={async () => {
                    await api.deleteDataset(d.id);
                    refresh();
                  }}
                >
                  Delete
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
