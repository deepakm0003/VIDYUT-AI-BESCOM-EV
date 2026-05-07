from __future__ import annotations

from pathlib import Path
from typing import Callable

import numpy as np

from ml.rl_env import BESCOMFeederEnv, EPISODE_STEPS

try:
    from stable_baselines3.common.callbacks import BaseCallback
except ImportError:  # Allows CLI/help imports before dependencies are installed.
    BaseCallback = object


def require_stable_baselines3():
    try:
        from stable_baselines3 import PPO
        from stable_baselines3.common.callbacks import EvalCallback
        from stable_baselines3.common.vec_env import DummyVecEnv, SubprocVecEnv
    except ImportError as exc:
        raise ImportError(
            "stable-baselines3 is required to train VIDYUTPPOAgent. "
            "Install backend requirements with: pip install -r backend/requirements.txt"
        ) from exc
    return PPO, EvalCallback, DummyVecEnv, SubprocVecEnv


class TrainingProgressCallback(BaseCallback):
    def __init__(self, print_every: int = 10_000) -> None:
        if hasattr(super(), "__init__"):
            super().__init__()
        self.print_every = print_every
        self._last_print = 0

    def _on_step(self) -> bool:
        if self.num_timesteps - self._last_print >= self.print_every:
            self._last_print = self.num_timesteps
            print(f"PPO training progress: {self.num_timesteps:,} timesteps")
        return True


class VIDYUTPPOAgent:
    def __init__(
        self,
        env_factory: Callable[[], BESCOMFeederEnv],
        model_dir: Path,
        n_envs: int = 8,
        tensorboard_log: Path | None = None,
        seed: int = 42,
    ) -> None:
        self.env_factory = env_factory
        self.model_dir = Path(model_dir)
        self.n_envs = n_envs
        self.seed = seed
        self.tensorboard_log = tensorboard_log or self.model_dir / "tensorboard"
        self.model_path = self.model_dir / "ppo_agent.zip"
        self.best_model_dir = self.model_dir / "ppo_best"
        self.PPO, self.EvalCallback, self.DummyVecEnv, self.SubprocVecEnv = require_stable_baselines3()
        self.env = self._make_vec_env(n_envs)
        self.eval_env = self.DummyVecEnv([env_factory])
        self.model = self.PPO(
            "MlpPolicy",
            self.env,
            learning_rate=3e-4,
            n_steps=2048,
            batch_size=64,
            n_epochs=10,
            gamma=0.99,
            gae_lambda=0.95,
            clip_range=0.2,
            ent_coef=0.01,
            policy_kwargs=dict(net_arch=[256, 256, 128]),
            tensorboard_log=str(self.tensorboard_log),
            seed=seed,
            verbose=1,
        )

    def _make_vec_env(self, n_envs: int):
        factories = [self.env_factory for _ in range(n_envs)]
        if n_envs <= 1:
            return self.DummyVecEnv(factories)
        return self.SubprocVecEnv(factories)

    def train(self, total_timesteps: int = 500_000) -> Path:
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.best_model_dir.mkdir(parents=True, exist_ok=True)
        eval_callback = self.EvalCallback(
            self.eval_env,
            best_model_save_path=str(self.best_model_dir),
            log_path=str(self.model_dir / "ppo_eval"),
            eval_freq=10_000,
            deterministic=True,
            render=False,
        )
        progress_callback = TrainingProgressCallback(print_every=10_000)
        self.model.learn(
            total_timesteps=total_timesteps,
            callback=[progress_callback, eval_callback],
            tb_log_name="vidyut_ppo",
        )
        self.model.save(self.model_path)
        return self.model_path

    @classmethod
    def load(cls, model_path: Path, env_factory: Callable[[], BESCOMFeederEnv], model_dir: Path, n_envs: int = 1):
        instance = cls(env_factory=env_factory, model_dir=model_dir, n_envs=n_envs)
        instance.model = instance.PPO.load(model_path, env=instance.env)
        instance.model_path = Path(model_path)
        return instance

    def get_power_envelopes(self, obs: np.ndarray, horizon_hours: int = 6) -> dict[str, list[float]]:
        intervals = horizon_hours * 4
        current_obs = np.asarray(obs, dtype=np.float32)
        envelopes = {
            "slow": [],
            "fast": [],
            "bmtc": [],
        }
        base_limits = {"slow": 22.0, "fast": 150.0, "bmtc": 150.0}
        temp_env = self.env_factory()
        temp_env.reset()

        for _ in range(intervals):
            action, _ = self.model.predict(current_obs, deterministic=True)
            action = np.clip(np.asarray(action).reshape(-1), 0.0, 1.0)
            for idx, station_type in enumerate(["slow", "fast", "bmtc"]):
                envelopes[station_type].append(float(base_limits[station_type] * (1.0 - action[idx])))
            current_obs, _, terminated, truncated, _ = temp_env.step(action)
            if terminated or truncated:
                break
        return envelopes

    def evaluate(self, n_episodes: int = 50) -> dict[str, float]:
        rewards = []
        overload_events = []
        soc_violations = []
        off_peak_pct = []

        for episode in range(n_episodes):
            env = self.env_factory()
            obs, _ = env.reset(seed=self.seed + episode)
            done = False
            episode_reward = 0.0
            while not done:
                action, _ = self.model.predict(obs, deterministic=True)
                obs, reward, terminated, truncated, _ = env.step(action)
                episode_reward += reward
                done = terminated or truncated

            rewards.append(episode_reward)
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

    def close(self) -> None:
        self.env.close()
        self.eval_env.close()
