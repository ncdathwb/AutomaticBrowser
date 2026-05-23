"""General application settings (headless mode, etc.) stored in settings.json."""

import json
from dataclasses import dataclass
from pathlib import Path

SETTINGS_FILENAME = "settings.json"


@dataclass
class AppSettings:
    headless: bool = False


def _settings_path(data_dir: Path) -> Path:
    return data_dir / SETTINGS_FILENAME


def load_settings(data_dir: Path) -> AppSettings:
    path = _settings_path(data_dir)
    if not path.is_file():
        return AppSettings()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return AppSettings(
            headless=bool(data.get("headless", False)),
        )
    except (json.JSONDecodeError, OSError):
        return AppSettings()


def save_settings(data_dir: Path, settings: AppSettings) -> bool:
    data_dir.mkdir(parents=True, exist_ok=True)
    try:
        _settings_path(data_dir).write_text(
            json.dumps({"headless": settings.headless}, indent=2),
            encoding="utf-8",
        )
        return True
    except OSError:
        return False
