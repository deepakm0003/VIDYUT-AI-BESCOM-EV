from __future__ import annotations

from pathlib import Path

import pandas as pd


class ProphetForecaster:
    def __init__(self, zone: str, model_dir: Path, changepoint_prior_scale: float = 0.08) -> None:
        try:
            from prophet import Prophet
        except ImportError as exc:
            raise ImportError("prophet is required for ProphetForecaster. Install backend/requirements.txt.") from exc

        self.zone = zone
        self.model_dir = Path(model_dir)
        self.model = Prophet(
            interval_width=0.9,
            changepoint_prior_scale=changepoint_prior_scale,
            yearly_seasonality=True,
            weekly_seasonality=False,
            daily_seasonality=False,
        )
        self.model.add_seasonality(name="weekly", period=7, fourier_order=8)
        self.model.add_seasonality(name="daily", period=1, fourier_order=12)
        self.model.add_seasonality(name="ev_adoption_trend", period=365.25, fourier_order=4)
        for regressor in ["temperature_c", "is_holiday", "ev_density_per_km2", "is_peak_hour"]:
            self.model.add_regressor(regressor)
        self.regressors = ["temperature_c", "is_holiday", "ev_density_per_km2", "is_peak_hour"]
        self.forecast = None

    def fit(self, df: pd.DataFrame) -> "ProphetForecaster":
        required = {"ds", "y", *self.regressors}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"Prophet input missing columns: {sorted(missing)}")
        train_df = df[["ds", "y", *self.regressors]].copy()
        train_df["ds"] = pd.to_datetime(train_df["ds"])
        train_df = train_df.sort_values("ds").dropna()
        self.model.fit(train_df)
        return self

    def predict(self, periods: int, future_regressors_df: pd.DataFrame) -> pd.DataFrame:
        future = future_regressors_df.copy()
        if "ds" not in future:
            future = self.model.make_future_dataframe(periods=periods, freq="15min")
            for regressor in self.regressors:
                future[regressor] = future_regressors_df[regressor].iloc[-1]
        future["ds"] = pd.to_datetime(future["ds"])
        self.forecast = self.model.predict(future[["ds", *self.regressors]])
        return self.forecast[["ds", "yhat", "yhat_lower", "yhat_upper"]]

    def decompose(self) -> dict[str, list[float]]:
        if self.forecast is None:
            raise ValueError("Call predict() before decompose().")
        components = {}
        for name in ["trend", "weekly", "daily", "holidays"]:
            if name in self.forecast:
                components[name] = self.forecast[name].tolist()
        return components

    def save(self) -> Path:
        from prophet.serialize import model_to_json

        self.model_dir.mkdir(parents=True, exist_ok=True)
        path = self.model_dir / f"prophet_{self.zone}.json"
        path.write_text(model_to_json(self.model), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: Path, zone: str | None = None) -> "ProphetForecaster":
        from prophet.serialize import model_from_json

        instance = cls(zone or Path(path).stem.replace("prophet_", ""), Path(path).parent)
        instance.model = model_from_json(Path(path).read_text(encoding="utf-8"))
        return instance
