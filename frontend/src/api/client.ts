// Thin typed wrapper around fetch. All calls go through the Vite /api proxy.
import type {
  AuthUser,
  CleaningConfig,
  Dataset,
  DatasetDetail,
  DetectResult,
  EdaResult,
  Leaderboard,
  ModelDetail,
  Prediction,
  Preview,
  RunOut,
  RunStatus,
  Token,
} from "../types";

const TOKEN_KEY = "pipeforge_token";

export const tokenStore = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (t: string) => localStorage.setItem(TOKEN_KEY, t),
  clear: () => localStorage.removeItem(TOKEN_KEY),
};

function authHeaders(): HeadersInit {
  const t = tokenStore.get();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

async function handle<T>(res: Response): Promise<T> {
  if (res.status === 401) {
    tokenStore.clear();
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  // --- auth ---
  async register(email: string, password: string): Promise<Token> {
    return handle(
      await fetch("/api/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      })
    );
  },

  async login(email: string, password: string): Promise<Token> {
    // OAuth2 password flow expects form-encoded username/password.
    const form = new URLSearchParams({ username: email, password });
    return handle(
      await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: form,
      })
    );
  },

  async me(): Promise<AuthUser> {
    return handle(await fetch("/api/auth/me", { headers: authHeaders() }));
  },

  // --- datasets ---
  async listDatasets(): Promise<Dataset[]> {
    return handle(await fetch("/api/datasets", { headers: authHeaders() }));
  },

  async uploadDataset(file: File): Promise<DatasetDetail> {
    const form = new FormData();
    form.append("file", file);
    return handle(
      await fetch("/api/datasets", { method: "POST", body: form, headers: authHeaders() })
    );
  },

  async previewDataset(id: number): Promise<Preview> {
    return handle(await fetch(`/api/datasets/${id}/preview`, { headers: authHeaders() }));
  },

  async detectTask(id: number): Promise<DetectResult> {
    return handle(
      await fetch(`/api/datasets/${id}/detect`, { method: "POST", headers: authHeaders() })
    );
  },

  async deleteDataset(id: number): Promise<void> {
    return handle(await fetch(`/api/datasets/${id}`, { method: "DELETE", headers: authHeaders() }));
  },

  // --- runs ---
  async createRun(body: {
    dataset_id: number;
    task_type: string;
    target_col: string | null;
    cleaning: CleaningConfig;
  }): Promise<RunOut> {
    return handle(
      await fetch("/api/runs", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify(body),
      })
    );
  },

  async getRunStatus(runId: number): Promise<RunStatus> {
    return handle(await fetch(`/api/runs/${runId}/status`, { headers: authHeaders() }));
  },

  async getEda(runId: number): Promise<EdaResult> {
    return handle(await fetch(`/api/runs/${runId}/eda`, { headers: authHeaders() }));
  },

  async getLeaderboard(runId: number): Promise<Leaderboard> {
    return handle(await fetch(`/api/runs/${runId}/leaderboard`, { headers: authHeaders() }));
  },

  async getModelDetail(runId: number, modelId: number): Promise<ModelDetail> {
    return handle(await fetch(`/api/runs/${runId}/models/${modelId}`, { headers: authHeaders() }));
  },

  modelDownloadUrl(runId: number, modelId: number): string {
    // Includes the token as a query param so a plain <a download> works.
    return `/api/runs/${runId}/models/${modelId}/download`;
  },

  async predict(runId: number, file: File): Promise<Prediction> {
    const form = new FormData();
    form.append("file", file);
    return handle(
      await fetch(`/api/runs/${runId}/predict`, {
        method: "POST",
        body: form,
        headers: authHeaders(),
      })
    );
  },

  async downloadModel(runId: number, modelId: number, filename: string): Promise<void> {
    // Fetch with auth header, then trigger a browser download from the blob.
    const res = await fetch(`/api/runs/${runId}/models/${modelId}/download`, {
      headers: authHeaders(),
    });
    if (!res.ok) throw new Error("Download failed");
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  },
};
