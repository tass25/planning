"""Structured logging configuration using structlog."""

import logging
import sys
import os

import structlog


def configure_logging(log_file: str | None = None, json_output: bool = False):
    """Configure structlog for the project.

    Args:
        log_file: Optional path to a log file. If None, logs go to stdout only.
        json_output: If True, use JSONRenderer (production). Otherwise ConsoleRenderer (dev).
    """
    # Determine the renderer
    if json_output:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        renderer,
    ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
    )

    # Optionally set up stdlib file logging alongside structlog
    if log_file:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.INFO)
        logging.root.addHandler(file_handler)
