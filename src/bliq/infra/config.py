"""Configuration model and YAML loader."""

from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, ValidationError, model_validator

from bliq.infra.errors import ConfigError


class SymbolsConfig(BaseModel):
    default_mode: Literal["top", "all", "file"] = "top"
    default_top_n: int = Field(50, gt=0)


class AmihudConfig(BaseModel):
    interval: str = "5m"
    lookback_bars: int = Field(288, gt=0)


class MetricsConfig(BaseModel):
    depth_pcts: list[float]
    obi_levels: list[int]
    orderbook_limit: int = Field(gt=0)
    slippage_levels_usdt: list[float]
    max_slippage_bps: float = Field(gt=0)
    amihud: AmihudConfig
    taker_ratio_window: int = Field(gt=0)


class ScoreWeights(BaseModel):
    spread: float
    capacity: float
    amihud: float
    obi_stability: float

    @model_validator(mode="after")
    def _sum_to_one(self) -> ScoreWeights:
        total = self.spread + self.capacity + self.amihud + self.obi_stability
        if not math.isclose(total, 1.0, abs_tol=1e-6):
            raise ValueError(f"score_weights must sum to 1.0, got {total}")
        return self


class DataConfig(BaseModel):
    rest_base: str
    ws_base: str
    max_concurrent_requests: int = Field(gt=0)
    rate_limit_weight_per_min: int = Field(gt=0)
    retry_attempts: int = Field(ge=0)
    retry_backoff_base: float = Field(gt=0)


class StorageConfig(BaseModel):
    db_path: str
    wal_mode: bool = True


class LoggingConfig(BaseModel):
    level: str = "INFO"
    file: str = "logs/bliq.log"
    rotation: str = "10 MB"


class Config(BaseModel):
    symbols: SymbolsConfig
    metrics: MetricsConfig
    score_weights: ScoreWeights
    data: DataConfig
    storage: StorageConfig
    logging: LoggingConfig


def load_config(path: Path) -> Config:
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"config file not found: {path}")
    try:
        raw = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {path}: {exc}") from exc
    try:
        cfg = Config.model_validate(raw)
    except ValidationError as exc:
        # Unwrap pydantic errors so ConfigError messages are readable.
        msgs = "; ".join(e["msg"] for e in exc.errors())
        raise ConfigError(f"config validation failed: {msgs}") from exc
    db_override = os.environ.get("BLIQ_DB_PATH", "").strip()
    if db_override:
        cfg.storage.db_path = db_override
    return cfg
