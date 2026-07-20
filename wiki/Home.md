# PipeForge Wiki

Welcome to the **PipeForge** wiki â€” the end-to-end data science pipeline platform.
Upload data, and PipeForge ingests, cleans, explores, and (soon) trains and compares
models automatically.

## Navigation

- **[Getting Started](Getting-Started.md)** â€” install and run in 5 minutes.
- **[Concepts & Glossary](Glossary.md)** â€” datasets, runs, tasks, stages explained.
- **[FAQ](FAQ.md)** â€” common questions and troubleshooting.
- **[Roadmap](../docs/ROADMAP.md)** â€” what's built and what's next.

## Deep-dive docs

- [Architecture](../docs/ARCHITECTURE.md)
- [API Reference](../docs/API.md)
- [Security](../docs/SECURITY.md)
- [Deployment & Scaling](../docs/DEPLOYMENT.md)

## What PipeForge does today

1. **Ingest** any CSV / TSV / JSON / Excel / Parquet file and infer a typed schema.
2. **Detect** the likely problem type (regression, classification, time series) and target.
3. **Clean** the data â€” dedup, impute missing values, coerce dates, handle outliers.
4. **Explore** with an interactive EDA dashboard (distributions, correlations, target
   relationships, time-series plots) plus a downloadable HTML report.

Model training, a leaderboard, deep learning, and prediction arrive in the next
milestones â€” see the [Roadmap](../docs/ROADMAP.md).

## The 60-second mental model

> You (a **User**) upload a **Dataset**. You start a **Run** on it with a chosen
> **task type** + **target column** and cleaning options. The Run executes the
> **pipeline stages** and produces an **EDA** result (and, from Milestone 3, a
> **leaderboard** of trained models). Everything is scoped to your account.
