# Roadmap

PipeForge is built in milestones, each independently runnable.

| # | Milestone | Status |
| - | --------- | ------ |
| 1 | Skeleton + upload + schema inference + preview + task detection | âœ… done |
| 2 | Data cleaning/ETL + EDA (interactive charts + HTML report) | âœ… done |
| â€” | Platform hardening: auth, rate limiting, validation, sharding, scalable deploy | âœ… done |
| 3 | Tabular AutoML (regression/classification) + async job runner + leaderboard + predict/download | âœ… done |
| 4 | Time series + deep learning (PyTorch MLP & LSTM) competing in the leaderboard | â¬œ next |
| 5 | Hyperparameter tuning + model explainability (SHAP) + run comparison | ðŸŸ¡ tuning + SHAP shipped via the Agentic layer; run comparison pending |
| 6 | Polish: error states, config presets, packaging, observability | â¬œ |
| A | **Agentic AI layer** â€” specialist LLM agents (Advise / Chat / Copilot / Autopilot), pluggable provider, HP tuning + explainability | âœ… done |

---

## Milestone 3 â€” Tabular AutoML âœ…

Milestone 3 transforms PipeForge from an EDA tool into a complete **AutoML platform**. A
single API call now takes a dataset from upload through cleaning, EDA, multi-model
training, and evaluation â€” with the best model downloadable and ready for predictions on
new data.

### Pipeline modules shipped

| Module | What it does |
| ------ | ------------ |
| `pipeline/features.py` | `ColumnTransformer` preprocessor â€” impute + scale numeric, impute + one-hot categorical (up to 50 categories), datetime expansion (year/month/day/dow). Bundled with each model into a single picklable sklearn `Pipeline`. |
| `pipeline/model_zoo.py` | Defines classification & regression candidate zoos. **Classification:** Logistic Regression, Random Forest, Extra Trees, Gradient Boosting, XGBoost, LightGBM, KNN, Gaussian Naive Bayes. **Regression:** Linear Regression, Ridge, Random Forest, Extra Trees, Gradient Boosting, XGBoost, LightGBM, KNN. |
| `pipeline/train.py` | Orchestrates the sweep: holdout split (80/20, stratified for classification), fits each candidate inside a `Pipeline(preprocessor, model)`, collects metrics + eval-plot payloads, ranks by primary metric, extracts feature importance. |
| `pipeline/evaluate.py` | **Classification metrics:** accuracy, weighted F1, ROC AUC (binary + multi-class OVR). **Regression metrics:** RMSE, MAE, RÂ². **Plots:** confusion matrix, ROC curve, predicted-vs-actual scatter, residuals scatter, feature importance bar chart. |
| `pipeline/registry.py` | Persists the best model artifact (joblib) with metadata (task type, target, feature columns, class labels). Loads and runs predictions on new data at inference time. |

### Job runner

| Component | Details |
| --------- | ------- |
| `jobs/runner.py` | `ThreadPoolExecutor`-backed async runner. Each stage (loading â†’ cleaning â†’ EDA â†’ training â†’ finalizing) reports `stage` + `progress` (0â€“100) to the `Run` row so the frontend can poll `/api/runs/{id}/status`. |
| Error handling | Single-model failures are caught and logged; the remaining candidates continue. Full pipeline failures mark the run as `error` with a human-readable message. |
| Scaling path | In-process pool â†’ shared queue (Redis/RQ or Celery) for independent training workers (Milestone 4+). |

### New data model

- **`ModelResult`** table: `model_name`, `family` (linear/tree/boosting/neighbors/bayes),
  `metrics_json`, `plots_json`, `artifact_path`, `rank`. Linked to `Run` via
  `run_id` (one-to-many).
- **`Run.best_model_id`** â€” points to the rank-1 `ModelResult` for quick access.

### New API endpoints

| Method | Path | Description |
| ------ | ---- | ----------- |
| `POST` | `/api/runs` | Now **asynchronous** â€” returns immediately with `status: queued`, client polls `/status`. |
| `GET` | `/api/runs/{id}/status` | Returns `{ status, stage, progress, message, best_model_id }`. |
| `GET` | `/api/runs/{id}/leaderboard` | Ranked list of trained models with metrics; identifies the primary metric and best model. |
| `GET` | `/api/runs/{id}/models/{mid}` | Full model detail including eval-plot payloads (confusion matrix, ROC, residuals, feature importance). |
| `GET` | `/api/runs/{id}/models/{mid}/download` | Download the best model's joblib artifact. |
| `POST` | `/api/runs/{id}/predict` | Upload new rows (any supported format) and get predictions from the run's best model. |

### Frontend features

- **Live progress bar** â€” polls `/status` and shows stage + percentage during training.
- **Leaderboard table** â€” sortable model comparison with metrics and rank badges.
- **Eval charts** â€” Plotly visualizations: confusion matrix heatmap, ROC curve, residuals
  scatter, predicted-vs-actual scatter, feature importance bar chart.
- **Model download** â€” one-click `.joblib` download of the best model artifact.
- **Predict widget** â€” upload a file and get predictions using the trained best model.

### Dependencies added

```
scikit-learn>=1.4    # ML framework + preprocessing
xgboost>=2.0         # Gradient boosting (XGBoost)
lightgbm>=4.3        # Gradient boosting (LightGBM)
joblib>=1.3          # Model artifact serialization
```

---

## Milestone 4 detail (next)

- `pipeline/deep.py` â€” PyTorch tabular MLP (a leaderboard entry) and LSTM/GRU for time
  series, with early stopping, scored on the same holdout.
- Classical time series via `statsforecast` / Prophet; lag/rolling features.
- Optional: swap the in-process pool for a shared queue (Redis/RQ or Celery) so training
  workers scale independently of the API.
- New dependencies in `requirements-ml.txt` (torch, statsforecast, etc.).

---

## Milestone A — Agentic AI layer ✅

Specialist LLM agents that reason about the decisions the pipeline otherwise hardcodes,
while the tested `pipeline/*` code still executes them. Additive — with no provider
configured, the classic pipeline is unchanged. Full reference: [AGENTS.md](AGENTS.md).

Built on **PydanticAI** (typed agent outputs) with a **pluggable provider** (Claude /
OpenAI / Ollama) and per-agent model configuration.

### Delivered in phases

| Phase | What shipped | Smoke test |
| ----- | ------------ | ---------- |
| 0 | Provider factory, deps, tool wrappers, config secrets | — |
| 1 | **Advise** + **Chat** modes, agent settings UI | `smoke_agent.py` |
| 2 | **Copilot** — approval gates (cleaning, modeling) with park/resume | `smoke_copilot.py` |
| 3 | **Autopilot** — Forge Master runs end-to-end unattended | `smoke_autopilot.py` |
| 4 | Hyperparameter tuning + model explainability (SHAP) read by the Critic | `smoke_phase4.py` |

### What it added

- **7 agents**: Forge Master (orchestrator), Profiler, Cleaning, EDA Analyst, Modeling
  Strategist, Evaluation Critic, Data Analyst (chat).
- **4 tables**: `agent_sessions`, `agent_messages` (decision trace), `agent_proposals`
  (Copilot gates), `agent_configs` (per-user model overrides).
- **API**: `/api/agents/*` — sessions, streamed/polled trace, chat messages, approval
  gate, and per-agent model config.
- **Frontend**: an Agent tab (live agent board + reasoning/chat + approval gate) and a
  `/settings/agents` model-configuration page.
- **Pipeline extensions**: `train_models` model-subset + hyperparameter search;
  `pipeline/explain.py` (SHAP when available, coefficient/importance fallback).

Ties off the tuning + explainability parts of Milestone 5; run comparison remains.
