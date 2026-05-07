from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch
from sklearn.preprocessing import StandardScaler
from torch import nn
from torch.nn.utils import clip_grad_norm_
from torch.utils.data import DataLoader, Dataset
from tqdm import tqdm


class BiLSTMForecaster(nn.Module):
    """Attention-based BiLSTM forecaster for feeder load sequences."""

    def __init__(
        self,
        input_size: int = 40,
        horizon: int = 96,
        projection_size: int = 128,
        hidden_size: int = 256,
        num_layers: int = 2,
        dropout: float = 0.2,
    ) -> None:
        super().__init__()
        self.input_projection = nn.Linear(input_size, projection_size)
        self.lstm = nn.LSTM(
            input_size=projection_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            dropout=dropout,
            batch_first=True,
            bidirectional=True,
        )
        self.attention = nn.Sequential(
            nn.Linear(hidden_size * 2, hidden_size),
            nn.Tanh(),
            nn.Linear(hidden_size, 1),
        )
        self.output_head = nn.Sequential(
            nn.Linear(hidden_size * 2, 128),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(128, horizon),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        projected = torch.relu(self.input_projection(x))
        sequence, _ = self.lstm(projected)
        attention_logits = self.attention(sequence).squeeze(-1)
        attention_weights = torch.softmax(attention_logits, dim=1).unsqueeze(-1)
        context = torch.sum(sequence * attention_weights, dim=1)
        return self.output_head(context)


class SlidingWindowDataset(Dataset):
    def __init__(
        self,
        frame: pd.DataFrame,
        feature_columns: list[str],
        target_column: str = "load_mw",
        window: int = 96,
        horizon: int = 96,
        stride: int = 4,
        max_sequences: int | None = None,
        seed: int = 42,
    ) -> None:
        self.feature_columns = feature_columns
        self.target_column = target_column
        self.window = window
        self.horizon = horizon
        self.stride = stride
        self.frame = frame.sort_values(["feeder_id", "timestamp"]).reset_index(drop=True)
        self.starts: list[tuple[int, int]] = []

        rng = np.random.default_rng(seed)
        for _, group in self.frame.groupby("feeder_id", observed=True, sort=False):
            indices = group.index.to_numpy()
            max_start = len(indices) - window - horizon + 1
            if max_start <= 0:
                continue
            group_starts = [(int(indices[start]), start) for start in range(0, max_start, stride)]
            self.starts.extend(group_starts)

        if max_sequences and len(self.starts) > max_sequences:
            chosen = rng.choice(len(self.starts), size=max_sequences, replace=False)
            self.starts = [self.starts[int(index)] for index in np.sort(chosen)]

        self.features = self.frame[feature_columns].to_numpy(dtype=np.float32)
        self.target = self.frame[target_column].to_numpy(dtype=np.float32)
        self.timestamps = self.frame["timestamp"].to_numpy()
        self.feeder_ids = self.frame["feeder_id"].astype(str).to_numpy()

    def __len__(self) -> int:
        return len(self.starts)

    def __getitem__(self, index: int) -> tuple[torch.Tensor, torch.Tensor]:
        frame_start, _ = self.starts[index]
        x = self.features[frame_start : frame_start + self.window]
        y = self.target[frame_start + self.window : frame_start + self.window + self.horizon]
        return torch.from_numpy(x), torch.from_numpy(y)

    def metadata_for_index(self, index: int) -> dict:
        frame_start, _ = self.starts[index]
        target_index = frame_start + self.window + self.horizon - 1
        return {
            "timestamp": self.timestamps[target_index],
            "feeder_id": self.feeder_ids[target_index],
            "y_true": float(self.target[target_index]),
        }


@dataclass
class LSTMTrainingResult:
    model: BiLSTMForecaster
    checkpoint_path: Path
    curve_path: Path
    history: dict[str, list[float]]
    predictions: pd.DataFrame
    feature_columns: list[str]


def chronological_split(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    unique_times = np.array(sorted(pd.to_datetime(df["timestamp"]).unique()))
    train_end = unique_times[int(len(unique_times) * 0.70)]
    val_end = unique_times[int(len(unique_times) * 0.85)]
    train = df[df["timestamp"] < train_end].copy()
    val = df[(df["timestamp"] >= train_end) & (df["timestamp"] < val_end)].copy()
    test = df[df["timestamp"] >= val_end].copy()
    return train, val, test


def scale_splits(
    train: pd.DataFrame,
    val: pd.DataFrame,
    test: pd.DataFrame,
    feature_columns: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, StandardScaler]:
    scaler = StandardScaler()
    scaler.fit(train[feature_columns].replace([np.inf, -np.inf], np.nan).fillna(0.0))

    scaled = []
    for split in (train, val, test):
        split = split.copy()
        values = split[feature_columns].replace([np.inf, -np.inf], np.nan).fillna(0.0)
        split.loc[:, feature_columns] = scaler.transform(values)
        scaled.append(split)
    return scaled[0], scaled[1], scaled[2], scaler


def train_lstm_forecaster(
    df: pd.DataFrame,
    feature_columns: list[str],
    zone: str,
    horizon_label: str,
    horizon_steps: int,
    model_dir: Path,
    epochs: int = 60,
    batch_size: int = 256,
    patience: int = 10,
    learning_rate: float = 1e-3,
    max_train_sequences: int = 200_000,
    max_eval_sequences: int = 40_000,
    device: str | None = None,
) -> LSTMTrainingResult:
    model_dir.mkdir(parents=True, exist_ok=True)
    device = device or ("cuda" if torch.cuda.is_available() else "cpu")

    train_df, val_df, test_df = chronological_split(df)
    train_df, val_df, test_df, _ = scale_splits(train_df, val_df, test_df, feature_columns)

    train_ds = SlidingWindowDataset(
        train_df,
        feature_columns=feature_columns,
        horizon=horizon_steps,
        max_sequences=max_train_sequences,
    )
    val_ds = SlidingWindowDataset(
        val_df,
        feature_columns=feature_columns,
        horizon=horizon_steps,
        max_sequences=max_eval_sequences,
    )
    test_ds = SlidingWindowDataset(
        test_df,
        feature_columns=feature_columns,
        horizon=horizon_steps,
        max_sequences=max_eval_sequences,
    )

    if not train_ds or not val_ds:
        raise ValueError("Not enough rows to build LSTM train/validation sequences.")

    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True, drop_last=False)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False, drop_last=False)

    model = BiLSTMForecaster(input_size=len(feature_columns), horizon=horizon_steps).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=max(1, epochs))
    criterion = nn.HuberLoss()

    checkpoint_path = model_dir / f"lstm_{zone}_{horizon_label}.pt"
    curve_path = model_dir / f"lstm_training_curve_{zone}_{horizon_label}.png"
    best_val_loss = float("inf")
    patience_left = patience
    history = {"train_loss": [], "val_loss": []}

    for epoch in range(1, epochs + 1):
        model.train()
        train_losses = []
        for x_batch, y_batch in tqdm(train_loader, desc=f"lstm train {epoch}/{epochs}", leave=False):
            x_batch = x_batch.to(device)
            y_batch = y_batch.to(device)
            optimizer.zero_grad(set_to_none=True)
            loss = criterion(model(x_batch), y_batch)
            loss.backward()
            clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()
            train_losses.append(float(loss.detach().cpu()))

        model.eval()
        val_losses = []
        with torch.no_grad():
            for x_batch, y_batch in val_loader:
                x_batch = x_batch.to(device)
                y_batch = y_batch.to(device)
                val_losses.append(float(criterion(model(x_batch), y_batch).detach().cpu()))

        scheduler.step()
        train_loss = float(np.mean(train_losses))
        val_loss = float(np.mean(val_losses))
        history["train_loss"].append(train_loss)
        history["val_loss"].append(val_loss)

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            patience_left = patience
            torch.save(
                {
                    "model_state_dict": model.state_dict(),
                    "input_size": len(feature_columns),
                    "horizon": horizon_steps,
                    "feature_columns": feature_columns,
                    "zone": zone,
                    "horizon_label": horizon_label,
                    "val_loss": best_val_loss,
                },
                checkpoint_path,
            )
        else:
            patience_left -= 1
            if patience_left <= 0:
                break

    if checkpoint_path.exists():
        checkpoint = torch.load(checkpoint_path, map_location=device)
        model.load_state_dict(checkpoint["model_state_dict"])

    plt.figure(figsize=(9, 5))
    plt.plot(history["train_loss"], label="train")
    plt.plot(history["val_loss"], label="validation")
    plt.title(f"BiLSTM Training Curve - {zone} {horizon_label}")
    plt.xlabel("Epoch")
    plt.ylabel("Huber loss")
    plt.legend()
    plt.tight_layout()
    plt.savefig(curve_path, dpi=150)
    plt.close()

    predictions = predict_dataset(model, test_ds, device=device)
    return LSTMTrainingResult(
        model=model,
        checkpoint_path=checkpoint_path,
        curve_path=curve_path,
        history=history,
        predictions=predictions,
        feature_columns=feature_columns,
    )


def predict_dataset(model: BiLSTMForecaster, dataset: SlidingWindowDataset, device: str) -> pd.DataFrame:
    if not dataset:
        return pd.DataFrame(columns=["timestamp", "feeder_id", "y_true", "y_pred"])

    loader = DataLoader(dataset, batch_size=512, shuffle=False)
    rows = []
    model.eval()
    cursor = 0
    with torch.no_grad():
        for x_batch, _ in loader:
            preds = model(x_batch.to(device)).detach().cpu().numpy()[:, -1]
            for pred in preds:
                meta = dataset.metadata_for_index(cursor)
                meta["y_pred"] = float(pred)
                rows.append(meta)
                cursor += 1
    return pd.DataFrame(rows)
