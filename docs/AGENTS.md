# Agentic AI Layer

PipeForge's pipeline is deterministic: every decision — task type, target, imputation,
which models — is a hardcoded heuristic. The **agentic layer** adds specialist LLM agents
that *reason* about those decisions, while the tested `pipeline/*` code still *executes*
them. The layer is **additive**: with the provider off (the default) nothing here runs and
the classic pipeline is unchanged.

> **Core principle.** The existing pipeline functions become the agents' *tools*. Agents
> decide; the pipeline executes. Nothing about a classic (`mode=off`) run changes.

Built on [PydanticAI](https://ai.pydantic.dev/) so every agent has a **typed output
contract** and the provider is **pluggable** (Anthropic / OpenAI / Ollama).

---

## Modes

Chosen per session (or per run). Set the default with `PIPEFORGE_AGENT_DEFAULT_MODE`.

| Mode | What it does | Human involvement |
| ---- | ------------ | ----------------- |
| `off` | Classic deterministic pipeline (default). | — |
| **Advise** | The EDA Analyst narrates insights, risks, and hypotheses over a completed run. No execution change. | Read-only |
| **Chat** | Conversational Q&A over the dataset and results. | Interactive |
| **Copilot** | Drives the pipeline, **pausing at two approval gates** (cleaning, modeling) for you to approve/edit/reject. | Approval gates |
| **Autopilot** | The Forge Master runs the whole pipeline end-to-end, unattended (gates auto-approved). | None |

Advise and Chat are read-only and run request/response. Copilot and Autopilot run on the
background job pool and are polled via `GET /sessions/{id}`.

---

## The agents

Each is a PydanticAI `Agent` with a typed `output_type` and a tool allowlist (read-only
tools for Advise/Chat; the write path runs through the orchestrator, not the LLM).

| Agent | Job | Model tier (default) | Output |
| ----- | --- | -------------------- | ------ |
| **Forge Master** (orchestrator) | Sequences the run, delegates, decides stop/pause | Opus 4.8 | `RunSummary` |
| **Profiler** | Infers task type + target, flags data quality | Haiku 4.5 | `ProfileReport` |
| **Cleaning Agent** | Proposes a per-column cleaning strategy | Haiku 4.5 | `CleaningPlan` |
| **EDA Analyst** | Narrates insights / risks / hypotheses | Opus 4.8 | `EdaNarrative` |
| **Modeling Strategist** | Picks the model subset, split, and tuning grids | Opus 4.8 | `ModelingPlan` |
| **Evaluation Critic** | Recommends a model, warns on leakage/overfit, reads explanations | Opus 4.8 | `EvalVerdict` |
| **Data Analyst** (chat) | Conversational Q&A (read-only) | Sonnet 5 | streamed text |

Specialists return typed Pydantic objects that the orchestrator hands forward as the next
agent's input — no free-text parsing between agents.

### The flow (Copilot / Autopilot)

```
profile → [cleaning gate] → clean + EDA → [modeling gate] → train → critique → done
```

The state machine ([`app/agents/copilot.py`](../backend/app/agents/copilot.py)) is
**resumable** — it derives its position from the DB, so Copilot parks at a gate
(`status=awaiting_approval`) and picks up again when you approve. Autopilot runs the same
machine with the gates auto-approved.

---

## Tools = pipeline wrappers

[`app/agents/tools.py`](../backend/app/agents/tools.py) — each tool is a thin
`RunContext` wrapper over an already-tested function. Only **schema/stats/samples** are
sent to the LLM, never the full dataset.

| Tool | Wraps | Access |
| ---- | ----- | ------ |
| `profile_dataset` | `ingest.infer_schema` + stats | read |
| `suggest_task_and_target` | `detect.suggest` | read |
| `query_eda_stats` | `eda.run_eda` / `Run.eda_json` | read |
| `list_candidate_models` | `model_zoo.zoo_for` | read |
| `read_leaderboard` / `read_model_detail` | `ModelResult` rows | read |
| `read_feature_importance` | stored SHAP / importance (`explain.top_drivers`) | read |
| `run_cleaning` / `run_training` | `clean.clean_dataframe` / `train.train_models` | write (orchestrator only) |

---

## Hyperparameter tuning & explainability (Phase 4)

- The **Modeling Strategist** may propose `tune: true` plus per-model grids
  (`hyperparameters`). Training then runs a capped `RandomizedSearchCV` per model and keeps
  the best estimator; chosen params land in `plots.tuned_params`. See
  [`pipeline/train.py`](../backend/app/pipeline/train.py) `_tune`.
- **Explainability**: [`pipeline/explain.py`](../backend/app/pipeline/explain.py) computes
  SHAP attributions when the optional `shap` package is installed and degrades to
  coefficient/importance otherwise. The **Critic** reads these via `read_feature_importance`
  to check for leakage (a single dominant feature) and reports `key_drivers`.

---

## Data model

Four additive tables ([`app/models.py`](../backend/app/models.py)):

- **`agent_sessions`** — one interaction: `mode`, `status`, `current_agent` (drives the live
  UI), `error_json`.
- **`agent_messages`** — the full decision/conversation trace (role, agent, content, tool
  call, status). The UI derives per-agent status from this.
- **`agent_proposals`** — Copilot approval gates: stage config + status
  (pending/approved/edited/rejected).
- **`agent_configs`** — per-user, per-agent model overrides (provider, model, enabled,
  max_steps).

---

## API (`/api/agents`)

All routes require auth and are per-user isolated. When the provider is `off` they return 503.

| Method | Path | Purpose |
| ------ | ---- | ------- |
| `POST` | `/sessions` | Start a session `{mode, run_id|dataset_id}`. Advise runs synchronously; copilot/autopilot start a background job. |
| `GET` | `/sessions/{id}` | Session detail + trace + any pending approval gate. |
| `POST` | `/sessions/{id}/messages` | Send a chat message (chat mode). |
| `POST` | `/sessions/{id}/approve` | Approve / edit / reject the pending Copilot gate, then resume. |
| `GET` / `PUT` | `/config` | Per-agent model configuration (merged over system defaults). |

---

## Frontend

- **Agent tab** on the run page ([`pages/RunEdaPage.tsx`](../frontend/src/pages/RunEdaPage.tsx))
  — mode toggle (Advise / Chat / Copilot / Autopilot), the live **AgentBoard** (per-agent
  `idle → working → done → error`), the **AgentPanel** (reasoning + chat), and the
  **ProposalGate** approval form for Copilot.
- **Agent settings** at `/settings/agents`
  ([`pages/AgentSettingsPage.tsx`](../frontend/src/pages/AgentSettingsPage.tsx)) — per-agent
  provider/model dropdowns, enable toggle, step cap.

---

## Configuration

All via `PIPEFORGE_*` environment variables (or a `.env` in `backend/`). See
[`app/config.py`](../backend/app/config.py).

| Variable | Default | Notes |
| -------- | ------- | ----- |
| `PIPEFORGE_LLM_PROVIDER` | `off` | `off` \| `anthropic` \| `openai` \| `google` \| `ollama` \| `openai_compatible` |
| `PIPEFORGE_LLM_API_KEY` | — | **Secret.** Generic key for the active provider. Server-side only; never sent to the frontend. |
| `PIPEFORGE_ANTHROPIC_API_KEY` | — | Optional per-provider key (falls back to `LLM_API_KEY`). |
| `PIPEFORGE_OPENAI_API_KEY` | — | Optional per-provider key. |
| `PIPEFORGE_GOOGLE_API_KEY` | — | Optional per-provider key (Gemini). |
| `PIPEFORGE_LLM_BASE_URL` | — | Required for `openai_compatible`; also used by Ollama / proxies. |
| `PIPEFORGE_LLM_MODEL_ORCHESTRATOR` | `claude-opus-4-8` | Forge Master. Any model name your provider serves. |
| `PIPEFORGE_LLM_MODEL_ANALYST` | `claude-opus-4-8` | EDA Analyst / Modeling / Critic. |
| `PIPEFORGE_LLM_MODEL_CHEAP` | `claude-haiku-4-5` | Profiler / Cleaning. |
| `PIPEFORGE_LLM_MODEL_CHAT` | `claude-sonnet-5` | Chat. |
| `PIPEFORGE_AGENT_MAX_STEPS` | `12` | Cost guard. |
| `PIPEFORGE_AGENT_DEFAULT_MODE` | `advise` | — |

The model-name settings accept **any** string the chosen provider serves (e.g.
`gemini-2.0-flash`, `gpt-4o`, `claude-opus-4-8`, `llama3.1`). Per-agent provider + model
overrides set in the settings UI take precedence over these defaults — so you can even run
different agents on different providers, using the optional per-provider keys above.

### Adding a provider

Providers live in one registry: `PROVIDERS` in
[`app/agents/providers.py`](../backend/app/agents/providers.py). Each entry is a label, an
env key setting, a builder branch, and a curated model list. Anthropic, OpenAI, Google
(Gemini), Ollama, and any OpenAI-compatible gateway (`openai_compatible` + `LLM_BASE_URL`)
ship out of the box; adding another is a single registry entry plus a builder branch.

---

## How to run

### 1. Install dependencies

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt          # core API
pip install -r requirements-ml.txt       # ML stack (needed for training / SHAP)
pip install -r requirements-agents.txt   # PydanticAI + provider SDK
```

Install only the provider SDK you use — `anthropic` (default) and/or `openai` (also covers
Ollama, which is OpenAI-compatible) are listed in `requirements-agents.txt`.

### 2. Configure a provider

Pick any provider and set its model + key in the environment (or a `.env` in `backend/`):

```powershell
# Anthropic (Claude)
$env:PIPEFORGE_LLM_PROVIDER = "anthropic"
$env:PIPEFORGE_LLM_API_KEY  = "sk-ant-..."

# OpenAI (GPT)
$env:PIPEFORGE_LLM_PROVIDER = "openai"
$env:PIPEFORGE_LLM_API_KEY  = "sk-..."
$env:PIPEFORGE_LLM_MODEL_ANALYST = "gpt-4o"      # set the model names you want

# Google (Gemini)  — pip install "pydantic-ai-slim[google]"
$env:PIPEFORGE_LLM_PROVIDER = "google"
$env:PIPEFORGE_LLM_API_KEY  = "AIza..."
$env:PIPEFORGE_LLM_MODEL_ANALYST = "gemini-2.0-flash"
```

For a **local, no-external-service** setup use Ollama, or any OpenAI-compatible gateway
(vLLM, LM Studio, a proxy) via `openai_compatible`:

```powershell
$env:PIPEFORGE_LLM_PROVIDER = "ollama"
$env:PIPEFORGE_LLM_BASE_URL = "http://localhost:11434/v1"
# then set each agent's model to a local one (e.g. llama3.1) in /settings/agents
```

**Mixing providers:** set the optional per-provider keys (`PIPEFORGE_ANTHROPIC_API_KEY`,
`PIPEFORGE_OPENAI_API_KEY`, `PIPEFORGE_GOOGLE_API_KEY`) and choose a provider + model per
agent at `/settings/agents` — e.g. Gemini for cheap sub-tasks, Claude for the Critic.

Leaving `PIPEFORGE_LLM_PROVIDER` unset (`off`) keeps the classic pipeline fully working;
the Agent tab shows a "configure a provider" prompt.

### 3. Start the app

```powershell
# backend (from backend/)
uvicorn app.main:app --reload --port 8000

# frontend (from frontend/, in another terminal)
npm install
npm run dev
```

New agent tables are created automatically on startup (`init_db`). Open a completed run,
click the **Agent** tab, and pick a mode. Configure per-agent models at `/settings/agents`.

### 4. Verify without a key (smoke tests)

Each phase has a smoke test that runs the real agent wiring against PydanticAI's
`TestModel` — no API key, no network. From `backend/`:

```powershell
python smoke_agent.py       # Advise: EDA Analyst end-to-end over the real pipeline
python smoke_copilot.py     # Copilot: gate → approve → clean+EDA → next gate
python smoke_autopilot.py   # Autopilot: profile → … → critique → done (training stubbed)
python smoke_phase4.py      # tuning forwarded + explainability + critic drivers
```

> The `_autopilot` / `_phase4` tests stub the training call so they need neither an API key
> nor the ML stack; a real run trains through the same `runner.train_and_persist` path.
