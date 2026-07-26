<div align="center">

# 🛠️ PipeForge

### *The Autonomous, End-to-End Data Science & AutoML Pipeline Platform*

[![Build Status](https://img.shields.io/badge/build-passing-2ea44f?style=for-the-badge&logo=github-actions&logoColor=white)](.github/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](#)
[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18-20232A?style=for-the-badge&logo=react&logoColor=61DAFB)](https://react.dev/)
[![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)](#)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](#)

<p align="center">
  <b>Upload your raw dataset and let PipeForge automate ETL, Exploratory Analysis, Model Training, Leaderboard Selection, and Deployment predictions.</b>
</p>

[Key Features](#-key-features) •
[Pipeline Workflow](#-pipeline-workflow) •
[Agentic AI Layer](#-agentic-ai-layer) •
[AutoML Capabilities](#-automl-capabilities--model-matrix) •
[Tech Stack](#-technology-stack) •
[Quick Start](#-quick-start) •
[Docs Hub](#-documentation-hub)

---

</div>

## 💡 Overview

Building production-grade machine learning pipelines is notoriously time-consuming. Data scientists routinely spend hours on repetitive boilerplate: schema inference, missing value imputation, categorical encoding, feature scaling, model selection, hyperparameter tuning, and metric visualization.

**PipeForge** eliminates this friction. It provides an automated, end-to-end platform that ingests raw tabular datasets and generates fully-evaluated, deployment-ready machine learning artifacts with zero manual effort—enhanced with an optional **Agentic AI Layer** powered by LLMs.

---

## ⚡ Key Features

- ⚡ **Zero-Touch Automated Ingestion & ETL:** Intelligent schema detection, automatic imputation, outlier filtering, datetime feature extraction, and one-hot/label encoding.
- 🎯 **Automated ML Leaderboards:** Benchmark and evaluate candidate model families per run for both Classification and Regression problems.
- 🤖 **Agentic AI Engine:** 5 specialized LLM agents (Profiler, Cleaning Agent, EDA Analyst, Modeling Strategist, Evaluation Critic) orchestrated by a **Forge Master**.
- 📈 **Rich Visual Analytics:** Automatic confusion matrices, ROC/AUC curves, residual plots, feature importances, and SHAP explainability visualizations powered by Plotly.
- 📦 **Deployable Production Artifacts:** Save complete transformation and model pipelines as single unified `.joblib` bundles for instant inference.
- 🔒 **Enterprise Scalability:** Stateless FastAPI behind Nginx load balancing, PostgreSQL persistence, Redis-backed rate limiting, and Alembic-managed migrations — `--scale backend=N` for any N.
- 🛡️ **Production-Grade Security:** **OAuth 2.0 / OIDC single sign-on** (Google, Microsoft, GitHub) via authorization code + PKCE, short-lived access tokens with **rotating refresh tokens and reuse detection**, **role-based access control** (viewer / user / admin), identity-keyed rate limiting, structured JSON logging with request-id tracing, and a queryable **audit trail**. See [SECURITY.md](docs/SECURITY.md).

---

## 🔄 Pipeline Workflow

```
 ┌─────────────┐     ┌────────────────┐     ┌───────────────┐     ┌─────────────────┐     ┌──────────────────┐
 │  Data File  │ ──► │ Ingest & Clean │ ──► │ Feature Eng.  │ ──► │ AutoML Training │ ──► │ Leaderboard &    │
 │ (CSV/Parquet)     │     (ETL)      │     │  & Encoding   │     │  (8 Candidates) │     │ Best Artifact    │
 └─────────────┘     └────────────────┘     └───────────────┘     └─────────────────┘     └──────────────────┘
                                                                                                   │
                                                                                                   ▼
                                                                                           ┌──────────────────┐
                                                                                           │  Deploy & Predict│
                                                                                           └──────────────────┘
```

---

## 🤖 Agentic AI Layer

PipeForge features an optional, pluggable LLM-driven **Agentic AI Layer** layered on top of its deterministic engine. The deterministic pipeline functions act as tools for LLM specialists:

```
                      ┌──────────────────────────────────┐
                      │  🤖 FORGE MASTER (Orchestrator)  │
                      └────────────────┬─────────────────┘
                                       │
        ┌───────────────┬──────────────┼───────────────┬───────────────┐
        ▼               ▼              ▼               ▼               ▼
 ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
 │  Profiler   │ │  Cleaning   │ │ EDA Analyst │ │  Modeling   │ │ Evaluation  │
 │   Agent     │ │   Agent     │ │   Agent     │ │ Strategist  │ │   Critic    │
 └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘
```

### 💬 Four Interactive AI Modes

| Mode | Behavior & Description |
| :--- | :--- |
| **💡 Advise** | Narrates key data insights, detects anomalies, and explains pipeline run decisions post-execution. |
| **💬 Chat** | Conversational Q&A assistant over your uploaded dataset, pipeline metrics, and model performances. |
| **🕹️ Copilot** | Drives the pipeline step-by-step, pausing at each phase for user validation and custom decisions. |
| **🚀 Autopilot** | Autonomous execution where agents evaluate, choose strategies, and execute end-to-end unattended. |

> **Pluggable LLM Backends:** Supports Anthropic **Claude**, **OpenAI (GPT)**, **Google (Gemini)**, local **Ollama**, and any **OpenAI-compatible** gateway — set a provider, model, and key in `.env`, or configure a different provider/model per agent. Adding another provider is a single registry entry.
> For complete setup and architectural specifications, see **[docs/AGENTS.md](docs/AGENTS.md)**.

---

## 📊 AutoML Capabilities & Model Matrix

PipeForge benchmarks candidate models across standard algorithm families to surface the optimal predictor:

| Algorithm Family | Classification Models | Regression Models |
| :--- | :--- | :--- |
| **Linear Models** | Logistic Regression | Linear Regression, Ridge |
| **Tree-Based** | Random Forest, Extra Trees | Random Forest, Extra Trees |
| **Gradient Boosting** | Gradient Boosting, XGBoost, LightGBM | Gradient Boosting, XGBoost, LightGBM |
| **Nearest Neighbors** | K-Nearest Neighbors | K-Nearest Neighbors |
| **Naive Bayes** | Gaussian Naive Bayes | — |

---

## 🏗️ Technology Stack

| Layer | Technologies |
| :--- | :--- |
| **Frontend** | React 18, Vite, TypeScript, Plotly.js |
| **Backend API** | FastAPI, SQLAlchemy 2, Pydantic v2, Uvicorn |
| **Data Science & ML** | Scikit-Learn, XGBoost, LightGBM, Pandas, NumPy, SHAP, Joblib |
| **Agentic Framework** | PydanticAI · pluggable Claude / GPT / Gemini / Ollama |
| **Infrastructure** | PostgreSQL, Redis, Docker & Docker Compose, Nginx |

---

## 🚀 Quick Start

### 1. Backend Setup

```powershell
# Navigate to backend directory
cd backend

# Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Start backend server
uvicorn app.main:app --reload --port 8000
```
> 📍 API Interactive Docs will be accessible at: [http://localhost:8000/docs](http://localhost:8000/docs)

### 2. Frontend Setup

```powershell
# Navigate to frontend directory
cd frontend

# Install dependencies and start development server
npm install
npm run dev
```
> 📍 Web Interface will be live at: [http://localhost:5173](http://localhost:5173)

### 3. Enabling Agentic AI (Optional)

```powershell
cd backend
pip install -r requirements-agents.txt        # Install agent dependencies

# Configure your provider environment variables:
$env:PIPEFORGE_LLM_PROVIDER = "anthropic"      # anthropic | openai | google | ollama | openai_compatible
$env:PIPEFORGE_LLM_API_KEY  = "sk-ant-..."     # e.g. Gemini: provider "google", key "AIza...", model "gemini-2.0-flash"
```
> 📍 Learn more about setting up per-agent prompts and custom endpoints in **[docs/AGENTS.md](docs/AGENTS.md)**.

### 🐳 Full-Stack Docker Deployment

Run stateless backend replicas behind Nginx load balancer with PostgreSQL and Redis:

```bash
docker compose up --build --scale backend=3
```
> 📍 Gateway endpoint will be reachable at: [http://localhost:8080](http://localhost:8080)

---

## 📚 Documentation Hub

Explore detailed operational, security, and technical documentation:

| Guide | Content Description |
| :--- | :--- |
| 🏗️ **[Architecture](docs/ARCHITECTURE.md)** | System design, database schemas, state machines, & scalability. |
| 🤖 **[Agentic AI Layer](docs/AGENTS.md)** | Agent roles, tool definitions, prompt setup, & interaction modes. |
| 🔌 **[REST API Reference](docs/API.md)** | Endpoint specs, authentication schema, payload formats, & examples. |
| 🔒 **[Security & Hardening](docs/SECURITY.md)** | OAuth 2.0 / OIDC SSO, token rotation & revocation, RBAC, rate limiting, audit logging, CORS & input validation. |
| 🚢 **[Deployment Guide](docs/DEPLOYMENT.md)** | Docker orchestration, environment vars, & production deployment. |
| 🗺️ **[Project Roadmap](docs/ROADMAP.md)** | Feature milestones, planned integrations, & release history. |
| 📖 **[Project Wiki](wiki/Home.md)** | Detailed tutorials, user guides, and troubleshooting tips. |

---

<div align="center">

Made with ❤️ for Data Science & AI Automation • Released under the [MIT License](https://opensource.org/licenses/MIT)

</div>
