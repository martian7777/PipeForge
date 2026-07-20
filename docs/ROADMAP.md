# Roadmap

AutoDS is built in milestones, each independently runnable.

| # | Milestone | Status |
| - | --------- | ------ |
| 1 | Skeleton + upload + schema inference + preview + task detection | ✅ done |
| 2 | Data cleaning/ETL + EDA (interactive charts + HTML report) | ✅ done |
| — | Platform hardening: auth, rate limiting, validation, sharding, scalable deploy | ✅ done |
| 3 | Tabular AutoML (regression/classification) + async job runner + leaderboard | ⬜ next |
| 4 | Time series + deep learning (PyTorch MLP & LSTM) competing in the leaderboard | ⬜ |
| 5 | Predict on new data + model artifact download | ⬜ |
| 6 | Polish: error states, config presets, packaging, observability | ⬜ |

## Milestone 3 detail (next)

- `pipeline/features.py` — encoding, scaling, datetime expansion, lag features (TS).
- `pipeline/train.py` — AutoML orchestration. Default engine **FLAML** (light deps),
  optional **PyCaret**. Compares linear / tree / **XGBoost / LightGBM / CatBoost**.
- `jobs/runner.py` — `ProcessPoolExecutor` job runner; run stages report `stage` +
  `progress` to the DB; frontend polls `/api/runs/{id}/status`.
- `pipeline/evaluate.py` — task-specific metrics + eval-plot payloads.
- `ModelResult` rows populate a **leaderboard**; best model persisted to the artifact store.
- At fleet scale, swap the in-process pool for a shared queue (Redis/RQ or Celery) so
  training workers scale independently of the API.

## Milestone 4–5 detail

- `pipeline/deep.py` — PyTorch tabular MLP (tabular leaderboard entry) and LSTM/GRU for
  time series, with early stopping, scored on the same holdout.
- Classical time series via `statsforecast` / Prophet.
- `POST /api/runs/{id}/predict` — inference on newly uploaded rows using the best model;
  artifact download endpoint.
