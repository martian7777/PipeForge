# Concepts & Glossary

## Core entities

- **User** — an authenticated account. Owns datasets and runs; data is isolated per user.
- **Dataset** — an uploaded file plus its inferred **schema** (columns with dtype +
  semantic type + missing/unique counts).
- **Run** — one execution of the pipeline over a dataset with a chosen task type, target
  column, and cleaning config. Holds the EDA result and (later) trained models.
- **ModelResult** — one trained candidate model in a run's leaderboard (Milestone 3+).

## Problem / task types

- **Regression** — predict a continuous numeric target (RMSE / MAE / R²).
- **Classification** — predict a category/label (accuracy / F1 / AUC).
- **Time series** — forecast a numeric value over a datetime index (MAPE / RMSE).
- **Clustering** — group rows with no target (unsupervised).

## Semantic column types

Inferred during ingestion and used by later stages:

- **numeric** — integers/floats.
- **categorical** — discrete labels / low-cardinality strings.
- **datetime** — parsed dates/timestamps (drives time-series detection).
- **text** — high-cardinality free text.
- **boolean** — true/false.

## Pipeline stages

1. **Ingest** — load + type-infer the file.
2. **Detect** — suggest task type + target.
3. **Clean / ETL** — dedup, impute, coerce dates, drop constant columns, clip outliers.
4. **EDA** — summary + charts + HTML report.
5. **Features / Train / Evaluate** — *Milestone 3+*.

## Cleaning options

- **impute_numeric**: `median` · `mean` · `zero` · `drop`
- **impute_categorical**: `mode` · `constant` · `drop`
- **outlier_method**: `none` · `iqr` (1.5×IQR clip) · `zscore` (±3σ clip)
- **drop_duplicates**, **drop_constant_columns**: booleans

## Platform terms

- **JWT** — stateless bearer token used for auth; enables horizontal scaling.
- **Sharded storage** — files stored under hashed subdirectories so no directory grows
  unbounded.
- **Load balancer** — the nginx gateway distributing `/api` requests across backend
  replicas.
- **Stateless replica** — a backend container with no local state, so any number can run
  in parallel.
