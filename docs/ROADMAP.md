# Roadmap

AutoDS is built in milestones, each independently runnable.

| # | Milestone | Status |
| - | --------- | ------ |
| 1 | Skeleton + upload + schema inference + preview + task detection | ✅ done |
| 2 | Data cleaning/ETL + EDA (interactive charts + HTML report) | ✅ done |
| — | Platform hardening: auth, rate limiting, validation, sharding, scalable deploy | ✅ done |
| 3 | Tabular AutoML (regression/classification) + async job runner + leaderboard + predict/download | ✅ done |
| 4 | Time series + deep learning (PyTorch MLP & LSTM) competing in the leaderboard | ⬜ next |
| 5 | Hyperparameter tuning + model explainability (SHAP) + run comparison | ⬜ |
| 6 | Polish: error states, config presets, packaging, observability | ⬜ |

---

## Milestone 3 — Tabular AutoML ✅

Milestone 3 transforms AutoDS from an EDA tool into a complete **AutoML platform**. A
single API call now takes a dataset from upload through cleaning, EDA, multi-model
training, and evaluation — with the best model downloadable and ready for predictions on
new data.

### Pipeline modules shipped

| Module | What it does |
| ------ | ------------ |
| `pipeline/features.py` | `ColumnTransformer` preprocessor — impute + scale numeric, impute + one-hot categorical (up to 50 categories), datetime expansion (year/month/day/dow). Bundled with each model into a single picklable sklearn `Pipeline`. |
| `pipeline/model_zoo.py` | Defines classification & regression candidate zoos. **Classification:** Logistic Regression, Random Forest, Extra Trees, Gradient Boosting, XGBoost, LightGBM, KNN, Gaussian Naive Bayes. **Regression:** Linear Regression, Ridge, Random Forest, Extra Trees, Gradient Boosting, XGBoost, LightGBM, KNN. |
| `pipeline/train.py` | Orchestrates the sweep: holdout split (80/20, stratified for classification), fits each candidate inside a `Pipeline(preprocessor, model)`, collects metrics + eval-plot payloads, ranks by primary metric, extracts feature importance. |
| `pipeline/evaluate.py` | **Classification metrics:** accuracy, weighted F1, ROC AUC (binary + multi-class OVR). **Regression metrics:** RMSE, MAE, R². **Plots:** confusion matrix, ROC curve, predicted-vs-actual scatter, residuals scatter, feature importance bar chart. |
| `pipeline/registry.py` | Persists the best model artifact (joblib) with metadata (task type, target, feature columns, class labels). Loads and runs predictions on new data at inference time. |

### Job runner

| Component | Details |
| --------- | ------- |
| `jobs/runner.py` | `ThreadPoolExecutor`-backed async runner. Each stage (loading → cleaning → EDA → training → finalizing) reports `stage` + `progress` (0–100) to the `Run` row so the frontend can poll `/api/runs/{id}/status`. |
| Error handling | Single-model failures are caught and logged; the remaining candidates continue. Full pipeline failures mark the run as `error` with a human-readable message. |
| Scaling path | In-process pool → shared queue (Redis/RQ or Celery) for independent training workers (Milestone 4+). |

### New data model

- **`ModelResult`** table: `model_name`, `family` (linear/tree/boosting/neighbors/bayes),
  `metrics_json`, `plots_json`, `artifact_path`, `rank`. Linked to `Run` via
  `run_id` (one-to-many).
- **`Run.best_model_id`** — points to the rank-1 `ModelResult` for quick access.

### New API endpoints

| Method | Path | Description |
| ------ | ---- | ----------- |
| `POST` | `/api/runs` | Now **asynchronous** — returns immediately with `status: queued`, client polls `/status`. |
| `GET` | `/api/runs/{id}/status` | Returns `{ status, stage, progress, message, best_model_id }`. |
| `GET` | `/api/runs/{id}/leaderboard` | Ranked list of trained models with metrics; identifies the primary metric and best model. |
| `GET` | `/api/runs/{id}/models/{mid}` | Full model detail including eval-plot payloads (confusion matrix, ROC, residuals, feature importance). |
| `GET` | `/api/runs/{id}/models/{mid}/download` | Download the best model's joblib artifact. |
| `POST` | `/api/runs/{id}/predict` | Upload new rows (any supported format) and get predictions from the run's best model. |

### Frontend features

- **Live progress bar** — polls `/status` and shows stage + percentage during training.
- **Leaderboard table** — sortable model comparison with metrics and rank badges.
- **Eval charts** — Plotly visualizations: confusion matrix heatmap, ROC curve, residuals
  scatter, predicted-vs-actual scatter, feature importance bar chart.
- **Model download** — one-click `.joblib` download of the best model artifact.
- **Predict widget** — upload a file and get predictions using the trained best model.

### Dependencies added

```
scikit-learn>=1.4    # ML framework + preprocessing
xgboost>=2.0         # Gradient boosting (XGBoost)
lightgbm>=4.3        # Gradient boosting (LightGBM)
joblib>=1.3          # Model artifact serialization
```

---

## Milestone 4 detail (next)

- `pipeline/deep.py` — PyTorch tabular MLP (a leaderboard entry) and LSTM/GRU for time
  series, with early stopping, scored on the same holdout.
- Classical time series via `statsforecast` / Prophet; lag/rolling features.
- Optional: swap the in-process pool for a shared queue (Redis/RQ or Celery) so training
  workers scale independently of the API.
- New dependencies in `requirements-ml.txt` (torch, statsforecast, etc.).
