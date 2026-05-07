# VIDYUT AI Backend

Complete FastAPI backend for VIDYUT AI - Machine Learning Optimization for EV Grid Integration.

## 📁 Project Structure

```
backend/
├── main.py                    # FastAPI app with startup events
├── requirements.txt           # Python dependencies
├── api/
│   ├── __init__.py
│   ├── schemas.py            # Pydantic v2 schemas for all endpoints
│   └── routes/
│       ├── __init__.py
│       ├── forecast.py       # Ensemble forecasting (LSTM + XGBoost + Prophet)
│       ├── scheduler.py      # MILP + RL load optimization
│       ├── sites.py          # Site selection & GIS scoring
│       ├── carbon.py         # Carbon credits & monetization
│       └── alerts.py         # Real-time alerts via SSE
└── data/
    ├── models/               # Pre-trained ML models
    ├── processed/            # Feature-engineered datasets
    └── raw/                  # Source data
```

## 🚀 Installation & Setup

### Prerequisites
- Python 3.9+
- pip or conda

### Install Dependencies

```bash
cd backend
pip install -r requirements.txt
```

### Key Dependencies
- **FastAPI 0.111.0** - Web framework
- **Uvicorn 0.30.1** - ASGI server
- **Pydantic 2.7.1** - Data validation
- **Pandas 2.2.2** - Data manipulation
- **PyTorch 2.3.1** - Deep learning (LSTM)
- **XGBoost 2.0.3** - Gradient boosting
- **Prophet 1.1.5** - Time series forecasting
- **Stable Baselines3 2.3.2** - RL algorithms
- **HiGHS 1.7.1** - MILP solver
- **SHAP 0.45.1** - Model explainability
- **GeoPandas 0.14.4** - Geospatial analysis

## ▶️ Running the Server

### Development Mode
```bash
python main.py
```

Or with uvicorn directly:
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### Production Mode
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

## 📚 API Endpoints

### Health Check
- **GET** `/health` - Server status and model load info
- **GET** `/` - Root endpoint with API overview

### Forecast (`/api/forecast`)
- **GET** `/zones` - All zones with current load status
- **POST** `/predict` - Ensemble forecast (48h, 24h, 4h, 1h horizons)
- **GET** `/accuracy` - Model accuracy metrics (MAPE, RMSE, MAE)
- **GET** `/feeder/{feeder_id}` - Feeder-level 24h forecast

### Scheduler (`/api/scheduler`)
- **GET** `/status` - Current scheduler status
- **POST** `/run` - Execute MILP + RL optimization
- **GET** `/bmtc-schedule` - BMTC bus depot charging sequence
- **POST** `/override` - Emergency curtailment/restore signal

### Sites (`/api/sites`)
- **GET** `/rankings` - Ranked sites for EVCS placement (top 20, filterable by zone)
- **GET** `/{ward_id}` - Full site detail with all 7 factor scores
- **GET** `/geojson` - GeoJSON for map rendering
- **POST** `/rescore` - Trigger background site re-scoring job
- **GET** `/coverage-gaps` - Identify policy gaps (>3km from EVCS)

### Carbon (`/api/carbon`)
- **GET** `/summary` - Total carbon credits, CO2, capex savings
- **GET** `/monthly` - Monthly breakdown with date range filter
- **GET** `/certificate/{month}` - BEE certificate for month
- **POST** `/compute` - Trigger carbon calculation for month
- **GET** `/projections` - 6-year financial projections
- **GET** `/peer-comparison` - Benchmark vs peer utilities

### Alerts (`/api/alerts`)
- **GET** `/stream` - Server-Sent Events (SSE) real-time alerts
- **GET** `/history` - Last 100 alerts from in-memory buffer
- **GET** `/feeders/status` - All 500 feeders: load %, headroom %, status
- **GET** `/summary` - Alert statistics
- **GET** `/feeders/{feeder_id}/timeline` - Alert history for specific feeder

## 🔧 Configuration

### Startup Events
The app loads all ML models at startup (not per-request):
1. **Ensemble Forecaster** - LSTM, XGBoost, Prophet models for 6 zones
2. **PPO RL Agent** - Power envelope generation
3. **Site Rankings** - Pre-computed GIS scores from parquet
4. **Carbon History** - Monthly carbon credit records

Startup completion message:
```
🎉 VIDYUT AI Backend Ready — All models loaded
📊 Models Loaded: 4/4
   • Ensemble Forecaster (6 zones): ✅
   • PPO RL Agent: ✅
   • Site Rankings: ✅
   • Carbon History: ✅
📡 API Endpoint: http://localhost:8000
📖 Docs: http://localhost:8000/docs
```

### CORS
All origins allowed for hackathon demo:
```python
allow_origins=["*"]
allow_methods=["*"]
allow_headers=["*"]
```

## 📖 Interactive Documentation

Once running, visit:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## 💾 Data Files

The `backend/data/` directory is excluded from source control and must be created locally when you clone the repository.

Expected local data structure:
```
backend/data/
├── models/
│   └── lstm_zone_1_24h.pt      # PyTorch LSTM checkpoint
├── processed/
│   ├── site_rankings.json      # Pre-computed site scores
│   ├── carbon_credits_history.json  # Historical carbon data
│   ├── carbon_credits_history.parquet
│   ├── feature_manifest.json   # Feature engineering config
│   ├── forecast_features.parquet
│   ├── scheduler_features.parquet
│   ├── site_rankings.parquet
│   └── site_scoring_features.parquet
└── raw/
    ├── ev_sessions.csv         # EV charging sessions
    ├── feeder_load_data.csv    # Historical feeder loads
    ├── vahan_ev_registrations.csv
    ├── bmtc_depot_schedule.csv
    ├── weather_data.csv
    ├── data_manifest.json
    └── feature_engineering.py
```

### Local Setup Instructions
1. Create the `backend/data/` folder locally.
2. Add your model checkpoint(s) to `backend/data/models/`.
3. Add raw and processed dataset files to the corresponding subfolders.
4. Confirm the backend can load the files before starting the server.

## 🔐 Authentication

Currently no authentication required (hackathon mode). For production:
1. Add OAuth2 with JWT tokens
2. Implement API key validation
3. Add role-based access control

## ⚠️ Error Handling

All endpoints return consistent error responses:
```json
{
  "detail": "Error message"
}
```

Error codes:
- **400** - Bad request (invalid parameters)
- **404** - Resource not found
- **500** - Internal server error

## 🧪 Testing

Run tests with pytest:
```bash
pytest tests/ -v
```

## 📈 Performance

- **Model loading**: ~5-10 seconds at startup
- **Forecast prediction**: ~200ms (ensemble)
- **Scheduler optimization**: ~500-2000ms (MILP solve)
- **Alert generation**: Real-time SSE stream (10s interval)

## 🐛 Troubleshooting

### Port Already in Use
```bash
# Kill process on port 8000
lsof -i :8000
kill -9 <PID>
```

### Model Loading Issues
- Check `data/` directory structure
- Verify PyTorch installation: `python -c "import torch; print(torch.__version__)"`
- Check parquet files: `python -c "import pandas as pd; pd.read_parquet('data/processed/...')"`

### CORS Errors
Browser CORS is already configured. If issues persist, check:
- Frontend origin in `allow_origins` list
- Request headers in Network tab

## 📝 Logging

Logs output to console with timestamp and level:
```
2026-05-07 10:15:30 - main - INFO - 🚀 Starting VIDYUT AI Backend...
2026-05-07 10:15:31 - main - INFO - ✅ Ensemble forecaster: 6 zones loaded
```

Change log level in `main.py`:
```python
logging.basicConfig(level=logging.DEBUG)  # DEBUG, INFO, WARNING, ERROR
```

## 🤝 Integration with Frontend

Frontend at `../frontend/` connects to these endpoints:
- POST `/api/forecast/predict` - Demand forecast panel
- POST `/api/scheduler/run` - Smart scheduler panel  
- GET `/api/sites/rankings` - Site intelligence panel
- GET `/api/carbon/summary` - Carbon credits panel
- GET `/api/alerts/stream` - Alert console (SSE)

## 📞 Support

For issues or questions, refer to:
- API docs: http://localhost:8000/docs
- Main README: `../README.md`
- Architecture: See docstrings in `main.py`

---

**VIDYUT AI** © 2026 - Machine Learning for EV Grid Optimization
