"""Persistence layer for ClockConfig.

Config file location: ~/.config/linux-clock-app/config.json

Public API:
    load() -> ClockConfig
    save(config: ClockConfig) -> None
"""
import json
import logging
import os
from pathlib import Path

from linux_clock_app.models import ClockConfig

logger = logging.getLogger(__name__)

CONFIG_DIR: Path = Path.home() / ".config" / "linux-clock-app"
CONFIG_FILE: Path = CONFIG_DIR / "config.json"


def _ensure_dir(directory: Path) -> None:
    """Create *directory* (and parents) if it does not already exist."""
    directory.mkdir(parents=True, exist_ok=True)


def load() -> ClockConfig:
    """Load ClockConfig from disk.

    Returns:
        The persisted config if the file exists and is valid JSON.
        A default ClockConfig if the file is absent.
        A default ClockConfig (with a WARNING log) if the file is corrupt.
    """
    _ensure_dir(CONFIG_DIR)

    if not CONFIG_FILE.exists():
        return ClockConfig()

    try:
        raw = CONFIG_FILE.read_text(encoding="utf-8")
        data = json.loads(raw)
        return ClockConfig.from_dict(data)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning(
            "Config file is corrupt (%s). Overwriting with defaults. Error: %s",
            CONFIG_FILE,
            exc,
        )
        return ClockConfig()


def save(config: ClockConfig) -> None:
    """Atomically write *config* to CONFIG_FILE.

    Writes to a .tmp file first, then uses os.replace() so the operation
    is atomic on POSIX systems (prevents partial writes being read back).
    """
    _ensure_dir(CONFIG_DIR)

    tmp_file: Path = CONFIG_FILE.with_suffix(".tmp")
    payload = json.dumps(config.to_dict(), indent=2, ensure_ascii=False)

    tmp_file.write_text(payload, encoding="utf-8")
    os.replace(tmp_file, CONFIG_FILE)
