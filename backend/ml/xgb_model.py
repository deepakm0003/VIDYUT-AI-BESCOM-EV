from __future__ import annotations

from pathlib import Path

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shap
from sklearn.model_selection import TimeSeriesSplit
from xgboost import XGBRegressor


class XGBForecaster:
    def __init__(
        self,
        zone: str,
        horizon: str,
        model_dir: Path,
        random_state: int = 42,
    ) -> None:
        self.zone = zone
        self.horizon = horizon
        self.model_dir = Path(model_dir)
        self.random_state = random_state
        self.model = XGBRegressor(
            n_estimators=500,
            max_depth=7,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            objective="reg:squarederror",
            tree_method="hist",
            random_state=random_state,
            n_jobs=-1,
            early_stopping_rounds=50,
        )
        self.feature_names: list[str] = []
        self.cv_scores: list[float] = []
        self.explainer = None

    def _prepare_features(self, X: pd.DataFrame, fit: bool = False) -> pd.DataFrame:
        prepared = X.copy()
        for column in prepared.columns:
            if pd.api.types.is_datetime64_any_dtype(prepared[column]):
                prepared[column] = prepared[column].astype("int64") // 10**9
            elif pd.api.types.is_categorical_dtype(prepared[column]) or prepared[column].dtype == object:
                prepared[column] = prepared[column].astype("category").cat.codes
            elif prepared[column].dtype == bool:
                prepared[column] = prepared[column].astype("int8")

        prepared = prepared.replace([np.inf, -np.inf], np.nan)
        medians = prepared.median(numeric_only=True)
        prepared = prepared.fillna(medians).fillna(0.0)
        if fit:
            self.feature_names = list(prepared.columns)
        else:
            for column in self.feature_names:
                if column not in prepared.columns:
                    prepared[column] = 0.0
            prepared = prepared[self.feature_names]
        return prepared

    def fit(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        eval_fraction: float = 0.15,
        max_rows: int = 800_000,
    ) -> "XGBForecaster":
        X_prepared = self._prepare_features(X, fit=True)
        y = y.astype(float)

        if len(X_prepared) > max_rows:
            keep = np.linspace(0, len(X_prepared) - 1, max_rows).astype(int)
            X_prepared = X_prepared.iloc[keep].reset_index(drop=True)
            y = y.iloc[keep].reset_index(drop=True)

        tscv = TimeSeriesSplit(n_splits=5)
        self.cv_scores = []
        for train_idx, val_idx in tscv.split(X_prepared):
            fold_model = XGBRegressor(**self.model.get_params())
            fold_model.fit(
                X_prepared.iloc[train_idx],
                y.iloc[train_idx],
                eval_set=[(X_prepared.iloc[val_idx], y.iloc[val_idx])],
                verbose=False,
            )
            pred = fold_model.predict(X_prepared.iloc[val_idx])
            mae = float(np.mean(np.abs(pred - y.iloc[val_idx].to_numpy())))
            self.cv_scores.append(mae)

        split = int(len(X_prepared) * (1.0 - eval_fraction))
        self.model.fit(
            X_prepared.iloc[:split],
            y.iloc[:split],
            eval_set=[(X_prepared.iloc[split:], y.iloc[split:])],
            verbose=False,
        )
        self.explainer = shap.TreeExplainer(self.model)
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return self.model.predict(self._prepare_features(X))

    def save(self) -> Path:
        self.model_dir.mkdir(parents=True, exist_ok=True)
        path = self.model_dir / f"xgb_{self.zone}_{self.horizon}.pkl"
        joblib.dump(
            {
                "model": self.model,
                "feature_names": self.feature_names,
                "cv_scores": self.cv_scores,
                "zone": self.zone,
                "horizon": self.horizon,
            },
            path,
        )
        return path

    @classmethod
    def load(cls, path: Path) -> "XGBForecaster":
        payload = joblib.load(path)
        instance = cls(payload["zone"], payload["horizon"], Path(path).parent)
        instance.model = payload["model"]
        instance.feature_names = payload["feature_names"]
        instance.cv_scores = payload.get("cv_scores", [])
        instance.explainer = shap.TreeExplainer(instance.model)
        return instance

    def save_shap_summary(self, X: pd.DataFrame, max_rows: int = 10_000) -> tuple[Path, dict[str, float]]:
        if self.explainer is None:
            self.explainer = shap.TreeExplainer(self.model)

        X_prepared = self._prepare_features(X)
        if len(X_prepared) > max_rows:
            X_prepared = X_prepared.sample(max_rows, random_state=self.random_state)

        shap_values = self.explainer.shap_values(X_prepared)
        mean_abs = np.abs(shap_values).mean(axis=0)
        ranking = pd.Series(mean_abs, index=X_prepared.columns).sort_values(ascending=False)
        top_10 = ranking.head(10).to_dict()

        self.model_dir.mkdir(parents=True, exist_ok=True)
        path = self.model_dir / f"xgb_shap_summary_{self.zone}_{self.horizon}.png"
        plt.figure(figsize=(10, 6))
        ranking.head(20).sort_values().plot(kind="barh")
        plt.title(f"XGBoost SHAP Importance - {self.zone} {self.horizon}")
        plt.xlabel("Mean absolute SHAP value")
        plt.tight_layout()
        plt.savefig(path, dpi=150)
        plt.close()
        return path, {key: float(value) for key, value in top_10.items()}

    def predict_with_explanation(self, X: pd.DataFrame) -> dict:
        if self.explainer is None:
            self.explainer = shap.TreeExplainer(self.model)

        X_prepared = self._prepare_features(X).head(1)
        prediction = float(self.model.predict(X_prepared)[0])
        shap_values = self.explainer.shap_values(X_prepared)[0]
        shap_dict = {
            feature: float(value)
            for feature, value in zip(X_prepared.columns, shap_values)
        }
        top_features = sorted(shap_dict, key=lambda feature: abs(shap_dict[feature]), reverse=True)[:10]
        return {
            "prediction": prediction,
            "shap_values": shap_dict,
            "top_features": top_features,
        }
