"""Shared configuration for voice benchmarks."""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent.parent
RESULTS_DIR = ROOT_DIR / "results"

load_dotenv(ROOT_DIR / ".env")


def get_openai_api_key() -> str:
    key = os.getenv("OPENAI_API_KEY", "")
    if not key:
        raise ValueError("OPENAI_API_KEY not set in environment or .env file")
    return key


def get_xai_api_key() -> str:
    key = os.getenv("XAI_API_KEY", "")
    if not key:
        raise ValueError("XAI_API_KEY not set in environment or .env file")
    return key


def get_anthropic_api_key() -> str:
    key = os.getenv("ANTHROPIC_API_KEY", "")
    if not key:
        raise ValueError("ANTHROPIC_API_KEY not set in environment or .env file")
    return key


def get_openai_model() -> str:
    return os.getenv("OPENAI_REALTIME_MODEL", "gpt-4o-realtime-preview-2025-06-03")


def get_xai_model() -> str:
    return os.getenv("XAI_REALTIME_MODEL", "grok-2-rt-audio")


def get_log_level() -> str:
    return os.getenv("LOG_LEVEL", "INFO")


def setup_logging(name: str = "voice-benchmarks") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )
        logger.addHandler(handler)
    logger.setLevel(get_log_level())
    return logger
