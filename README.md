# VIDYUT-AI

A demo repository for the VIDYUT AI platform, with a FastAPI backend and React frontend.

## 📌 Important Note
The `backend/data/` directory is intentionally excluded from git because it contains large datasets and model artifacts.

If you clone this repository, create the `backend/data/` folder locally and populate it with the required raw and processed data files before running the backend.

## 📁 Expected Local Data Layout
```
backend/data/
├── models/
│   └── lstm_zone_1_24h.pt
├── processed/
│   ├── bee_certificate_2024-01.json
│   ├── carbon_credits_history.json
│   ├── carbon_credits_history.parquet
│   ├── feature_manifest.json
│   ├── forecast_features.parquet
│   ├── scheduler_features.parquet
│   ├── site_rankings.json
│   ├── site_rankings.parquet
│   └── site_scoring_features.parquet
└── raw/
    ├── bmtc_depot_schedule.csv
    ├── data_manifest.json
    ├── ev_sessions.csv
    ├── feeder_load_data.csv
    ├── vahan_ev_registrations.csv
    └── weather_data.csv
```

## 🚀 Getting Started
1. Clone the repo.
2. Create `backend/data/` locally.
3. Add your dataset files and ML model checkpoint.
4. Install dependencies and run the backend.

# VIDYUT-AI
