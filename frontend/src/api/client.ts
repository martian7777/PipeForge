// Thin typed wrapper around fetch. All calls go through the Vite /api proxy.
//
// Token handling:
//   * The **access token** lives in module memory only -- never localStorage. It is
//     short-lived (15 min) and a XSS payload cannot read it out of storage.
//   * The **refresh token** is an HttpOnly cookie set by the backend, so JS never sees
//     it at all. `credentials: "include"` is what sends it on /api/auth calls.
//   * On a 401 the client transparently calls /api/auth/refresh once and replays the
//     original request. Concurrent 401s share a single in-flight refresh.
import type {
  AgentConfig,
  AgentConfigItem,
  AgentMessage,
  AgentSessionDetail,
  ApiErrorBody,
  AuditEntry,
  AuthOptions,
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
  Role,
  RunOut,
  RunStatus,
  SessionInfo,
  Token,
} from "../types";

/** An API failure carrying the backend's structured error envelope. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly type: string = "error",
    readonly requestId: string | null = null,
    readonly details?: unknown
  ) {
    super(message);
    this.name = "ApiError";
  }
}

let accessToken: string | null = null;
let onAuthLost: (() => void) | null = null;

export const tokenStore = {
  get: () => accessToken,
  set: (t: string) => {
    accessToken = t;
  },
  clear: () => {
    accessToken = null;
  },
  /** Called when the session can no longer be recovered, so the UI can redirect. */
  onLost: (cb: () => void) => {
    onAuthLost = cb;
  },
};

async function toApiError(res: Response): Promise<ApiError> {
  const requestId = res.headers.get("X-Request-ID");
  try {
    const body = (await res.json()) as Partial<ApiErrorBody>;
    const message =
      body.error?.message ??
      (typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail)) ??
      res.statusText;
    return new ApiError(
      message,
      res.status,
      body.error?.type ?? "error",
      body.error?.request_id ?? requestId,
      body.error?.details
    );
  } catch {
    return new ApiError(res.statusText || "Request failed", res.status, "error", requestId);
  }
}

// A single shared refresh promise, so ten parallel 401s cause one refresh, not ten.
let refreshInFlight: Promise<boolean> | null = null;

async function refreshAccessToken(): Promise<boolean> {
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      try {
        const res = await fetch("/api/auth/refresh", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: "{}",
        });
        if (!res.ok) return false;
        const token = (await res.json()) as Token;
        accessToken = token.access_token;
        return true;
      } catch {
        return false;
      } finally {
        // Release on the next tick so callers awaiting this promise all see the result.
        setTimeout(() => {
          refreshInFlight = null;
        }, 0);
      }
    })();
  }
  return refreshInFlight;
}

interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: BodyInit | null;
  /** Skip the automatic refresh-and-retry (used by the auth endpoints themselves). */
  noRetry?: boolean;
}

async function send(path: string, init: RequestOptions = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);

  const doFetch = () => fetch(path, { ...init, headers, credentials: "include" });

  let res = await doFetch();
  if (res.status === 401 && !init.noRetry) {
    if (await refreshAccessToken()) {
      headers.set("Authorization", `Bearer ${accessToken}`);
      res = await doFetch();
    } else {
      accessToken = null;
      onAuthLost?.();
    }
  }
  return res;
}

async function request<T>(path: string, init: RequestOptions = {}): Promise<T> {
  const res = await send(path, init);
  if (!res.ok) throw await toApiError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

function jsonInit(method: string, body: unknown): RequestOptions {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

export const api = {
  // --- auth ---
  /** Public: which sign-in methods this deployment offers. */
  async authOptions(): Promise<AuthOptions> {
    return request("/api/auth/options", { noRetry: true });
  },

  async register(email: string, password: string, fullName?: string): Promise<Token> {
    const token = await request<Token>("/api/auth/register", {
      ...jsonInit("POST", { email, password, full_name: fullName ?? null }),
      noRetry: true,
    });
    accessToken = token.access_token;
    return token;
  },

  async login(email: string, password: string): Promise<Token> {
    // OAuth2 password grant expects form-encoded username/password.
    const token = await request<Token>("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ username: email, password }),
      noRetry: true,
    });
    accessToken = token.access_token;
    return token;
  },

  /**
   * Exchange the HttpOnly refresh cookie for an access token. Used on page load and
   * after an SSO redirect, both of which arrive with only the cookie.
   */
  async restoreSession(): Promise<boolean> {
    return refreshAccessToken();
  },

  /** Full-page navigation: the OAuth flow must happen in the browser, not via fetch. */
  startSso(provider: string, next = "/"): void {
    window.location.href = `/api/auth/oauth/${provider}/authorize?next=${encodeURIComponent(next)}`;
  },

  async logout(): Promise<void> {
    try {
      await request<void>("/api/auth/logout", { method: "POST", noRetry: true });
    } finally {
      accessToken = null;
    }
  },

  async logoutEverywhere(): Promise<void> {
    try {
      await request<void>("/api/auth/logout-all", { method: "POST" });
    } finally {
      accessToken = null;
    }
  },

  async me(): Promise<AuthUser> {
    return request("/api/auth/me");
  },

  async mySessions(): Promise<SessionInfo[]> {
    return request("/api/auth/sessions");
  },

  async changePassword(currentPassword: string, newPassword: string): Promise<void> {
    return request("/api/auth/password", {
      ...jsonInit("POST", { current_password: currentPassword, new_password: newPassword }),
    });
  },

  // --- admin ---
  async adminListUsers(q?: string): Promise<AuthUser[]> {
    const query = q ? `?q=${encodeURIComponent(q)}` : "";
    return request(`/api/admin/users${query}`);
  },

  async adminSetRole(userId: number, role: Role): Promise<AuthUser> {
    return request(`/api/admin/users/${userId}/role`, jsonInit("PATCH", { role }));
  },

  async adminSetActive(userId: number, isActive: boolean): Promise<AuthUser> {
    return request(
      `/api/admin/users/${userId}/active`,
      jsonInit("PATCH", { is_active: isActive })
    );
  },

  async adminRevokeSessions(userId: number): Promise<void> {
    return request(`/api/admin/users/${userId}/revoke-sessions`, { method: "POST" });
  },

  async adminAuditLog(params: { event_prefix?: string; outcome?: string; limit?: number } = {}): Promise<
    AuditEntry[]
  > {
    const query = new URLSearchParams();
    if (params.event_prefix) query.set("event_prefix", params.event_prefix);
    if (params.outcome) query.set("outcome", params.outcome);
    query.set("limit", String(params.limit ?? 100));
    return request(`/api/admin/audit?${query}`);
  },

  // --- datasets ---
  async listDatasets(): Promise<Dataset[]> {
    return request("/api/datasets");
  },

  async uploadDataset(file: File): Promise<DatasetDetail> {
    const form = new FormData();
    form.append("file", file);
    return request("/api/datasets", { method: "POST", body: form });
  },

  async previewDataset(id: number): Promise<Preview> {
    return request(`/api/datasets/${id}/preview`);
  },

  async detectTask(id: number): Promise<DetectResult> {
    return request(`/api/datasets/${id}/detect`, { method: "POST" });
  },

  async deleteDataset(id: number): Promise<void> {
    return request(`/api/datasets/${id}`, { method: "DELETE" });
  },

  // --- runs ---
  async createRun(body: {
    dataset_id: number;
    task_type: string;
    target_col: string | null;
    cleaning: CleaningConfig;
  }): Promise<RunOut> {
    return request("/api/runs", jsonInit("POST", body));
  },

  async getRunStatus(runId: number): Promise<RunStatus> {
    return request(`/api/runs/${runId}/status`);
  },

  async getEda(runId: number): Promise<EdaResult> {
    return request(`/api/runs/${runId}/eda`);
  },

  async getLeaderboard(runId: number): Promise<Leaderboard> {
    return request(`/api/runs/${runId}/leaderboard`);
  },

  async getModelDetail(runId: number, modelId: number): Promise<ModelDetail> {
    return request(`/api/runs/${runId}/models/${modelId}`);
  },

  modelDownloadUrl(runId: number, modelId: number): string {
    return `/api/runs/${runId}/models/${modelId}/download`;
  },

  /** Open the generated EDA report in a new tab without putting a token in the URL. */
  async openReport(runId: number): Promise<void> {
    const res = await send(`/api/runs/${runId}/report`);
    if (!res.ok) throw await toApiError(res);
    const url = URL.createObjectURL(await res.blob());
    window.open(url, "_blank", "noopener,noreferrer");
    // Give the new tab time to load before releasing the object URL.
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
  },

  async predict(runId: number, file: File): Promise<Prediction> {
    const form = new FormData();
    form.append("file", file);
    return request(`/api/runs/${runId}/predict`, { method: "POST", body: form });
  },

  // --- agents ---
  async createAgentSession(body: {
    mode: string;
    run_id?: number;
    dataset_id?: number;
  }): Promise<AgentSessionDetail> {
    return request("/api/agents/sessions", jsonInit("POST", body));
  },

  async getAgentSession(id: number): Promise<AgentSessionDetail> {
    return request(`/api/agents/sessions/${id}`);
  },

  async sendAgentMessage(id: number, content: string): Promise<AgentMessage[]> {
    return request(`/api/agents/sessions/${id}/messages`, jsonInit("POST", { content }));
  },

  async approveProposal(
    id: number,
    decision: "approve" | "reject",
    edited_config?: Record<string, unknown>
  ): Promise<AgentSessionDetail> {
    return request(
      `/api/agents/sessions/${id}/approve`,
      jsonInit("POST", { decision, edited_config: edited_config ?? null })
    );
  },

  async getAgentConfig(): Promise<AgentConfig> {
    return request("/api/agents/config");
  },

  async updateAgentConfig(agents: AgentConfigItem[]): Promise<AgentConfig> {
    return request("/api/agents/config", jsonInit("PUT", { agents }));
  },

  async downloadModel(runId: number, modelId: number, filename: string): Promise<void> {
    // Goes through `send` so the auth header and refresh-retry apply, then turns the
    // authenticated response into a browser download.
    const res = await send(`/api/runs/${runId}/models/${modelId}/download`);
    if (!res.ok) throw await toApiError(res);
    const url = URL.createObjectURL(await res.blob());
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  },
};
