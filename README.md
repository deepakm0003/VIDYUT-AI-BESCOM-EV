# THEME 9 | BESCOM | AI for Bharat 2026
# VIDYUT AI
**Intelligent EV Charging Optimization & Infrastructure Planning Platform for BESCOM**  
**From Reactive Grid Management to Predictive EV Intelligence**

Hackathon Submission — PAN IIT AI for Bharat 2026  
Team: **Aight** | Theme 9 | Bengaluru, Karnataka

---

## Executive Summary
VIDYUT AI (Sanskrit: “electricity/lightning”) is a **non-invasive, AI-powered decision-support platform** that augments BESCOM’s operational stack without modifying source systems. It transforms EV charging from unmanaged demand spikes into a **predictive, grid-aware orchestration layer** spanning forecasting, scheduling, site planning, and carbon monetization.

This repository contains a full working demo:
- **Backend**: FastAPI APIs for forecasting, scheduler, GIS site intelligence, alerts (SSE), and carbon credits.
- **Frontend**: React dashboard for planners/operators (charts + maps + PDF exports).
- **Hackathon-friendly data strategy**: **No large data committed**. The backend auto-generates **small demo artifacts on first boot** so the app works immediately after clone (ideal for GitHub + Render).

---

## Key Capabilities (What the demo shows)
- **Part A — EV Demand Forecasting (Ensemble)**  
  Zone-level load forecasts with model weights and accuracy metrics.
- **Part A — Smart Scheduling (MILP + RL-ready interface)**  
  Tactical MILP scheduler endpoint; RL layer is architected and can be trained/plugged in.
- **Part B — Site Intelligence (GIS scoring)**  
  Site rankings, ward-level drill-down, and planner map views (demo dataset).
- **Carbon Credit Engine**  
  Monthly metrics + **downloadable BEE-style certificate PDF**.
- **Real-time Alerts (SSE)**  
  Live alert stream + feeder status polling + operator override endpoint.
- **Submission PDF Export**  
  One-click **Submission Report PDF** from the dashboard.

---

## Architecture (Five-layer view)
- **Presentation**: React + Vite planner dashboard
- **API Layer**: FastAPI REST + SSE
- **Intelligence**: Forecasting, scheduler, scoring, carbon modules
- **Data/Artifacts**: Local demo artifacts (generated on boot) + optional full pipeline
- **Ingestion (planned)**: Read-only adapters for SCADA / EV Mithra / VAHAN / Weather / GIS

---

## Quickstart (Recommended)

### Option A — One command pipeline
From repo root:

```bash
./run_pipeline.sh start
```

This starts:
- Frontend: `http://localhost:5173`
- Backend docs: `http://localhost:8000/docs`

### Option B — Setup + start (full local pipeline)

```bash
./run_pipeline.sh setup --skip-rl
./run_pipeline.sh start
```

Notes:
- `setup` runs synthetic data + feature engineering + model training scripts (demo/hackathon mode).
- Use `--skip-rl` on CPU machines to speed up setup.

---

## Backend (FastAPI)

### Run backend only

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # (Windows PowerShell: .venv\\Scripts\\Activate.ps1)
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### Demo data behavior (important)
The repo ignores `backend/data/` to avoid large files. Instead, on startup the backend will **auto-create minimal demo artifacts** if they are missing (so cloning the repo still “just works”).

---

## Frontend (React + Vite)

### Run frontend only

```bash
cd frontend
npm install
npm run dev
```

### API base URL (local vs deploy)
The frontend reads:
- `VITE_API_BASE` (recommended for deployment)
- falls back to `http://localhost:8000` for local dev

---

## Deliverables & Exports
- **Submission PDF**: Dashboard button downloads `/api/report/submission-report.pdf`
- **Carbon Certificate PDF**: `/api/carbon/certificate/{YYYY-MM}.pdf`

---

## Render Deployment (Recommended split deploy)

### Backend (Render Web Service)
- **Root Directory**: `backend`
- **Build Command**:
  - `pip install -r requirements.txt`
- **Start Command**:
  - `uvicorn main:app --host 0.0.0.0 --port $PORT`

Because demo artifacts are generated at startup, the backend can boot without committed datasets.

### Frontend (Render Static Site)
- **Root Directory**: `frontend`
- **Build Command**:
  - `npm install && npm run build`
- **Publish Directory**:
  - `dist`
- **Environment Variable**:
  - `VITE_API_BASE=<your-backend-render-url>`

---

## Repo Structure

```text
vidyut-ai/
├── backend/                 # FastAPI backend (APIs + demo bootstrap)
├── frontend/                # React dashboard (charts + maps)
├── run_pipeline.sh          # Setup/start/retrain/demo runner
└── .gitignore               # excludes backend/data/ and other artifacts
```

---

## License
Hackathon submission / demo repository. Add an explicit license if needed for open-source distribution.

