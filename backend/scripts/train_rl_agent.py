from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from loguru import logger


BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent
MODEL_DIR = BACKEND_DIR / "data" / "models"
PROCESSED_FEATURES = BACKEND_DIR / "data" / "processed" / "forecast_features.parquet"

sys.path.append(str(BACKEND_DIR))

from ml.rl_agent import VIDYUTPPOAgent  # noqa: E402
from ml.rl_env import BESCOMFeederEnv  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train VIDYUT AI PPO scheduling agent.")
    parser.add_argument("--timesteps", type=int, default=500_000)
    parser.add_argument("--n-envs", type=int, default=8)
    parser.add_argument("--eval-episodes", type=int, default=50)
    parser.add_argument("--zone", default="zone_1", choices=[f"zone_{idx}" for idx in range(1, 7)])
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def make_env_factory(zone: str, seed: int):
    def _factory() -> BESCOMFeederEnv:
        return BESCOMFeederEnv.from_processed_features(
            processed_path=PROCESSED_FEATURES,
            zone_id=zone,
            max_days=180,
            seed=seed,
        )

    return _factory


def evaluate_baseline(env_factory, n_episodes: int) -> dict[str, float]:
    rewards = []
    overload_events = []
    soc_violations = []
    off_peak_pct = []

    for episode in range(n_episodes):
        env = env_factory()
        _, _ = env.reset(seed=10_000 + episode)
        done = False
        reward_total = 0.0
        while not done:
            # No-RL greedy baseline: mild curtailment only during warning/peak periods,
            # moderate incentive to move private charging off peak.
            load_pct = env.current_load_mw / max(env.feeder_capacity_mw, 1e-6)
            if load_pct > 0.85:
                action = np.array([0.35, 0.45, 0.20, 0.70], dtype=np.float32)
            else:
                action = np.array([0.05, 0.10, 0.00, 0.35], dtype=np.float32)
            _, reward, terminated, truncated, _ = env.step(action)
            reward_total += reward
            done = terminated or truncated

        rewards.append(reward_total)
        overload_events.append(env.overload_events)
        soc_violations.append(env.soc_violations)
        off_peak_pct.append(env.off_peak_sessions / max(env.total_sessions, 1.0) * 100.0)

    return {
        "mean_reward": float(np.mean(rewards)),
        "std_reward": float(np.std(rewards)),
        "mean_overload_events": float(np.mean(overload_events)),
        "mean_soc_violations": float(np.mean(soc_violations)),
        "mean_off_peak_pct": float(np.mean(off_peak_pct)),
    }


def main() -> None:
    args = parse_args()
    logger.remove()
    logger.add(lambda message: print(message, end=""), level="INFO")
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    logger.info(
        "Starting PPO training zone={} timesteps={} n_envs={}",
        args.zone,
        args.timesteps,
        args.n_envs,
    )
    env_factory = make_env_factory(args.zone, args.seed)
    agent = VIDYUTPPOAgent(
        env_factory=env_factory,
        model_dir=MODEL_DIR,
        n_envs=args.n_envs,
        seed=args.seed,
    )

    model_path = agent.train(total_timesteps=args.timesteps)
    evaluation = agent.evaluate(n_episodes=args.eval_episodes)
    baseline = evaluate_baseline(env_factory, n_episodes=args.eval_episodes)
    agent.close()

    overload_reduction = (
        (baseline["mean_overload_events"] - evaluation["mean_overload_events"])
        / max(baseline["mean_overload_events"], 1e-6)
        * 100.0
    )
    report = {
        "zone": args.zone,
        "timesteps": args.timesteps,
        "n_envs": args.n_envs,
        "model_path": str(model_path),
        "evaluation": evaluation,
        "baseline_no_rl_greedy": baseline,
        "overload_events_reduction_pct": float(overload_reduction),
    }
    report_path = MODEL_DIR / "rl_training_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("\nVIDYUT PPO final evaluation")
    print(f"  mean episode reward: {evaluation['mean_reward']:.3f} +/- {evaluation['std_reward']:.3f}")
    print(f"  mean overload events: {evaluation['mean_overload_events']:.3f}")
    print(f"  mean SoC violations: {evaluation['mean_soc_violations']:.3f}")
    print(f"  mean off-peak pct: {evaluation['mean_off_peak_pct']:.2f}%")
    print(f"  baseline overload events: {baseline['mean_overload_events']:.3f}")
    print(f"  overload events reduction vs baseline: {overload_reduction:.2f}%")
    print(f"  saved model: {model_path}")
    print(f"  saved report: {report_path}")


if __name__ == "__main__":
    main()
