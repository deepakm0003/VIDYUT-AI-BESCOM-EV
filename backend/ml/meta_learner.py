from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge


def mape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    denominator = np.clip(np.abs(y_true), 1e-6, None)
    return float(np.mean(np.abs((y_true - y_pred) / denominator)) * 100.0)


@dataclass
class EnsembleMetaLearner:
    alpha: float = 1.0
    model: Ridge = field(default_factory=lambda: Ridge(alpha=1.0, positive=True))
    weights: dict[str, float] = field(
        default_factory=lambda: {"lstm": 1 / 3, "xgb": 1 / 3, "prophet": 1 / 3}
    )
    mape_history: dict[str, list[float]] = field(
        default_factory=lambda: {"lstm": [], "xgb": [], "prophet": [], "ensemble": []}
    )
    fitted: bool = False

    def fit(self, oof_predictions: pd.DataFrame, target: pd.Series | np.ndarray) -> "EnsembleMetaLearner":
        X = oof_predictions[["lstm", "xgb", "prophet"]].astype(float).fillna(method="ffill").fillna(method="bfill")
        y = np.asarray(target, dtype=float)
        self.model = Ridge(alpha=self.alpha, positive=True)
        self.model.fit(X, y)
        coefficients = np.maximum(self.model.coef_, 0.0)
        if coefficients.sum() > 0:
            self.weights = {
                name: float(value / coefficients.sum())
                for name, value in zip(["lstm", "xgb", "prophet"], coefficients)
            }
        self.fitted = True
        return self

    def update_weights(self, recent_errors_dict: dict[str, float]) -> dict[str, float]:
        model_names = ["lstm", "xgb", "prophet"]
        errors = np.array([max(float(recent_errors_dict.get(name, 1.0)), 1e-6) for name in model_names])
        inverse_error = 1.0 / errors
        exp_scores = np.exp(inverse_error - inverse_error.max())
        normalized = exp_scores / exp_scores.sum()
        self.weights = {name: float(weight) for name, weight in zip(model_names, normalized)}
        return self.weights

    def predict(self, X: pd.DataFrame | dict[str, np.ndarray]) -> dict:
        if isinstance(X, dict):
            predictions = {
                name: np.asarray(X[name], dtype=float)
                for name in ["lstm", "xgb", "prophet"]
            }
            stacked = pd.DataFrame(predictions)
        else:
            stacked = X[["lstm", "xgb", "prophet"]].astype(float)
            predictions = {name: stacked[name].to_numpy() for name in stacked.columns}

        weighted = sum(self.weights[name] * predictions[name] for name in ["lstm", "xgb", "prophet"])
        ridge_prediction = self.model.predict(stacked) if self.fitted else weighted
        ensemble = 0.5 * weighted + 0.5 * ridge_prediction if self.fitted else weighted
        return {
            "prediction": ensemble,
            "individual_predictions": predictions,
        }

    def get_weights(self) -> dict[str, float]:
        total = sum(self.weights.values())
        if not total:
            return {"lstm": 1 / 3, "xgb": 1 / 3, "prophet": 1 / 3}
        return {name: float(value / total) for name, value in self.weights.items()}

    def update_mape_tracking(self, y_true: np.ndarray, predictions: dict[str, np.ndarray]) -> dict[str, float]:
        weekly_scores = {}
        for name, pred in predictions.items():
            weekly_scores[name] = mape(y_true, pred)
            self.mape_history.setdefault(name, []).append(weekly_scores[name])
        return weekly_scores
