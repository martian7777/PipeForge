<div align="center">

# PipeForge 🛠️

**The End-to-End Data Science Pipeline Platform**

[![Build Status](https://img.shields.io/badge/build-passing-brightgreen)](#)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](#)
[![Milestone: 3](https://img.shields.io/badge/Milestone-3_AutoML-orange)](#)

*Upload data. Let PipeForge do the rest.*

</div>

---

## 🎯 The Hook
Building robust data science pipelines is time-consuming. Data scientists often spend hours writing boilerplate code to clean data, perform EDA, and train baseline models before even getting to the actual problem-solving.

## 🚨 The Problem
Every new dataset requires a repetitive, manual workflow: 
- Ingesting and inferring schemas
- Handling missing values and outliers
- Encoding categorical variables
- Training multiple models to establish a baseline
- Evaluating and comparing model performances

## 💡 The Solution: PipeForge
PipeForge automates the tedious parts of data science. Upload a data file, tell PipeForge what kind of problem it is (or let it guess), and it runs the full standard data science pipeline for you automatically:

**Ingest → Clean/ETL → EDA → AutoML Training → Best-Model Selection → Predict**

---

## ✨ Features & AutoML Capabilities (Milestone 3)

PipeForge trains **8 candidate models** per run, automatically handles feature engineering, and ranks them into a competitive leaderboard.

| Family | Classification | Regression |
| :--- | :--- | :--- |
| **Linear** | Logistic Regression | Linear Regression, Ridge |
| **Tree** | Random Forest, Extra Trees | Random Forest, Extra Trees |
| **Boosting** | Gradient Boosting, XGBoost, LightGBM | Gradient Boosting, XGBoost, LightGBM |
| **Neighbors** | K-Nearest Neighbors | K-Nearest Neighbors |
| **Bayes** | Gaussian Naive Bayes | — |

- **Zero-Touch Pipelines:** Numeric columns are imputed and scaled. Categoricals are imputed and one-hot encoded. Datetimes are expanded into robust features.
- **Persistent Artifacts:** The full pipeline is saved as a single `.joblib` artifact. Predictions on new data require no manual feature engineering.
- **Rich Evaluations:** Automatic generation of confusion matrices, ROC curves, predicted-vs-actual, residuals, and feature importance charts.
- **Scalable Architecture:** Designed for horizontal scaling with stateless backend replicas, Postgres, and Redis.

## 🏗️ Technology Stack

| Component | Stack |
| :--- | :--- |
| **Frontend** | React 18, Vite, TypeScript, Plotly |
| **Backend** | FastAPI, SQLAlchemy 2, Pydantic v2 |
| **Database** | SQLite (Dev) → PostgreSQL (Prod) |
| **Machine Learning** | Scikit-Learn, XGBoost, LightGBM |
| **Architecture** | Nginx load balancing, JWT stateless auth |

## 🚀 Quick Start (Local Dev)

### 1. Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```
*API docs available at: [http://localhost:8000/docs](http://localhost:8000/docs)*

### 2. Frontend

```powershell
cd frontend
npm install
npm run dev
```
*App running at: [http://localhost:5173](http://localhost:5173) (proxies /api to :8000)*

### 🐳 Run via Docker (Full Stack)

Launch 3 backend replicas behind an Nginx gateway with Postgres and Redis:
```bash
docker compose up --build --scale backend=3
```
*Access the load-balanced platform at [http://localhost:8080](http://localhost:8080).*

## 📚 Documentation & Resources

- 🏗️ [Architecture Overview](docs/ARCHITECTURE.md)
- 🔌 [REST API Reference](docs/API.md)
- 🔒 [Security & Hardening](docs/SECURITY.md)
- 🚢 [Deployment Guide](docs/DEPLOYMENT.md)
- 🗺️ [Project Roadmap](docs/ROADMAP.md)
- 📖 [Project Wiki](wiki/Home.md)
