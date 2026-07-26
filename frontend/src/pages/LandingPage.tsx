import { Link } from "react-router-dom";

/** Icons are inline SVG so the page pulls nothing from a third-party CDN. */
const ICON: Record<string, JSX.Element> = {
  bolt: (
    <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M13 2 4 14h7l-1 8 9-12h-7l1-8z" strokeLinejoin="round" />
    </svg>
  ),
  target: (
    <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="2">
      <circle cx="12" cy="12" r="9" />
      <circle cx="12" cy="12" r="5" />
      <circle cx="12" cy="12" r="1.5" fill="currentColor" />
    </svg>
  ),
  robot: (
    <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="2">
      <rect x="4" y="8" width="16" height="12" rx="3" />
      <path d="M12 8V4M9 14h.01M15 14h.01" strokeLinecap="round" />
    </svg>
  ),
  chart: (
    <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M4 20V10M10 20V4M16 20v-7M22 20H2" strokeLinecap="round" />
    </svg>
  ),
  box: (
    <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M21 8 12 3 3 8v8l9 5 9-5V8z" strokeLinejoin="round" />
      <path d="M3 8l9 5 9-5M12 13v8" />
    </svg>
  ),
  shield: (
    <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M12 3l8 3v6c0 4.5-3.2 7.9-8 9-4.8-1.1-8-4.5-8-9V6l8-3z" strokeLinejoin="round" />
      <path d="m9 12 2 2 4-4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
};

const FEATURES = [
  {
    icon: "bolt",
    title: "Zero-touch ingestion & ETL",
    body: "Schema detection, imputation, outlier filtering, datetime extraction, and encoding run automatically on upload.",
  },
  {
    icon: "target",
    title: "Automated ML leaderboards",
    body: "Candidate model families are benchmarked per run and ranked, for both classification and regression problems.",
  },
  {
    icon: "robot",
    title: "Agentic AI engine",
    body: "Five specialist LLM agents — Profiler, Cleaning, EDA Analyst, Modeling Strategist, Evaluation Critic — under a Forge Master orchestrator.",
  },
  {
    icon: "chart",
    title: "Rich visual analytics",
    body: "Confusion matrices, ROC/AUC curves, residual plots, feature importances, and SHAP explainability, rendered with Plotly.",
  },
  {
    icon: "box",
    title: "Deployable artifacts",
    body: "Transformation and model pipelines are saved as unified .joblib bundles, ready for immediate inference.",
  },
  {
    icon: "shield",
    title: "Production-grade security",
    body: "OAuth 2.0 / OIDC SSO, rotating refresh tokens with reuse detection, role-based access control, and a queryable audit trail.",
  },
];

const PIPELINE = [
  { step: "Upload", detail: "CSV / Parquet" },
  { step: "Ingest & clean", detail: "ETL" },
  { step: "Feature engineering", detail: "Encoding & scaling" },
  { step: "AutoML training", detail: "Candidate sweep" },
  { step: "Leaderboard", detail: "Best artifact" },
  { step: "Deploy & predict", detail: "Inference" },
];

const MODES = [
  { name: "Advise", body: "Narrates insights, flags anomalies, and explains the decisions a run made." },
  { name: "Chat", body: "Conversational Q&A over your dataset, pipeline metrics, and model performance." },
  { name: "Copilot", body: "Drives the pipeline step by step, pausing at each phase for your approval." },
  { name: "Autopilot", body: "Agents choose strategies and execute end to end, unattended." },
];

const MODELS = [
  { family: "Linear models", classification: "Logistic Regression", regression: "Linear Regression, Ridge" },
  { family: "Tree-based", classification: "Random Forest, Extra Trees", regression: "Random Forest, Extra Trees" },
  {
    family: "Gradient boosting",
    classification: "Gradient Boosting, XGBoost, LightGBM",
    regression: "Gradient Boosting, XGBoost, LightGBM",
  },
  { family: "Nearest neighbors", classification: "K-Nearest Neighbors", regression: "K-Nearest Neighbors" },
  { family: "Naive Bayes", classification: "Gaussian Naive Bayes", regression: "—" },
];

const STACK = [
  "React 18",
  "Vite",
  "TypeScript",
  "Plotly.js",
  "FastAPI",
  "SQLAlchemy 2",
  "Pydantic v2",
  "Scikit-Learn",
  "XGBoost",
  "LightGBM",
  "SHAP",
  "PydanticAI",
  "PostgreSQL",
  "Redis",
  "Docker",
  "Nginx",
];

export default function LandingPage() {
  return (
    <div className="landing">
      <header className="app-header">
        <span className="logo">
          Pipe<span>Forge</span>
        </span>
        <span className="tag">End-to-end data science pipeline platform</span>
        <div style={{ marginLeft: "auto", display: "flex", gap: 10 }}>
          <Link className="btn ghost" to="/login">
            Sign in
          </Link>
          <Link className="btn" to="/login">
            Get started
          </Link>
        </div>
      </header>

      <section className="hero">
        <span className="eyebrow">Autonomous AutoML</span>
        <h1>
          Upload a raw dataset.
          <br />
          Get a deployable model.
        </h1>
        <p className="hero-sub">
          PipeForge automates the whole path — ETL, exploratory analysis, model training, leaderboard
          selection, and prediction — so the hours normally lost to boilerplate go back into the problem
          you actually care about.
        </p>
        <div className="hero-cta">
          <Link className="btn lg" to="/login">
            Start a pipeline
          </Link>
          <a className="btn ghost lg" href="/api/docs" target="_blank" rel="noreferrer">
            Browse the API
          </a>
        </div>
      </section>

      <section className="landing-section">
        <h2 className="section-title">From file to forecast</h2>
        <ol className="flow">
          {PIPELINE.map((s, i) => (
            <li key={s.step} className="flow-step">
              <span className="flow-num">{i + 1}</span>
              <div>
                <b>{s.step}</b>
                <div className="subtle">{s.detail}</div>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <section className="landing-section">
        <h2 className="section-title">What you get</h2>
        <div className="feature-grid">
          {FEATURES.map((f) => (
            <div className="card feature" key={f.title}>
              <span className="feature-icon">{ICON[f.icon]}</span>
              <h3>{f.title}</h3>
              <p className="subtle">{f.body}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="landing-section">
        <h2 className="section-title">Four ways to work with the agents</h2>
        <p className="subtle section-lede">
          An optional LLM layer sits on top of the deterministic engine — the pipeline functions become
          tools the specialists call. Bring Claude, GPT, Gemini, a local Ollama model, or any
          OpenAI-compatible gateway.
        </p>
        <div className="mode-grid">
          {MODES.map((m) => (
            <div className="card mode" key={m.name}>
              <span className="badge">{m.name}</span>
              <p className="subtle">{m.body}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="landing-section">
        <h2 className="section-title">Models benchmarked every run</h2>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Algorithm family</th>
                <th>Classification</th>
                <th>Regression</th>
              </tr>
            </thead>
            <tbody>
              {MODELS.map((m) => (
                <tr key={m.family}>
                  <td>
                    <b>{m.family}</b>
                  </td>
                  <td>{m.classification}</td>
                  <td>{m.regression}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="landing-section">
        <h2 className="section-title">Built on</h2>
        <div className="pill-row">
          {STACK.map((t) => (
            <span className="badge" key={t}>
              {t}
            </span>
          ))}
        </div>
      </section>

      <section className="landing-section">
        <div className="card cta-card">
          <h2>Ready to forge a pipeline?</h2>
          <p className="subtle">Create an account and upload your first dataset in under a minute.</p>
          <Link className="btn lg" to="/login">
            Get started
          </Link>
        </div>
      </section>

      <footer className="landing-footer subtle">
        PipeForge · Released under the MIT License
      </footer>
    </div>
  );
}
