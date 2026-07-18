"""Logging helpers for command-line and Streamlit execution."""

from __future__ import annotations

import logging


def configure_logging(level: str = "INFO") -> None:
    """Configure concise timestamped logging without duplicate handlers."""

    resolved_level = getattr(logging, level.upper(), logging.INFO)
    root_logger = logging.getLogger()
    root_logger.setLevel(resolved_level)

    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if root_logger.handlers:
        for handler in root_logger.handlers:
            handler.setLevel(resolved_level)
            handler.setFormatter(formatter)
        return

    handler = logging.StreamHandler()
    handler.setLevel(resolved_level)
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)
