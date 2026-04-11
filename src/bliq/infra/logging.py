"""loguru setup — called once at CLI startup."""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

from bliq.infra.config import LoggingConfig


def setup_logging(cfg: LoggingConfig) -> None:
    logger.remove()
    logger.add(
        sys.stderr,
        level=cfg.level,
        format="<green>{time:HH:mm:ss}</green> | <level>{level:<7}</level> | "
        "<cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    )
    log_path = Path(cfg.file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger.add(
        log_path,
        level=cfg.level,
        rotation=cfg.rotation,
        enqueue=True,
        backtrace=False,
        diagnose=False,
    )
