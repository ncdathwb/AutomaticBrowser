import os
from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass
from pathlib import Path

APP_NAME = "AutoBrowser"
APP_VERSION = "0.1.0"

ENV_DATA_DIR = "AUTOBROWSER_DATA_DIR"
ENV_LOG_LEVEL = "AUTOBROWSER_LOG_LEVEL"
DEFAULT_DOTENV_FILE = Path(".env")

DEFAULT_LOG_LEVEL = "INFO"
VALID_LOG_LEVELS = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"}


def load_dotenv_file(
    path: Path = DEFAULT_DOTENV_FILE,
    env: MutableMapping[str, str] | None = None,
) -> None:
    current_env = os.environ if env is None else env

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("export "):
            line = line.removeprefix("export ").strip()

        key, separator, value = line.partition("=")
        key = key.strip()
        if not separator or not key or key in current_env:
            continue

        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]

        current_env[key] = value


def env_value(env: Mapping[str, str], key: str, default: str = "") -> str:
    return env.get(key, default).strip()


def resolve_app_data_dir(env: Mapping[str, str] | None = None) -> Path:
    current_env = os.environ if env is None else env
    configured_data_dir = env_value(current_env, ENV_DATA_DIR)
    if configured_data_dir:
        return Path(configured_data_dir).expanduser()

    local_app_data = env_value(current_env, "LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / APP_NAME

    return Path.home() / "AppData" / "Local" / APP_NAME


def resolve_log_level(env: Mapping[str, str] | None = None) -> str:
    current_env = os.environ if env is None else env
    log_level = env_value(current_env, ENV_LOG_LEVEL, DEFAULT_LOG_LEVEL).upper()
    return log_level if log_level in VALID_LOG_LEVELS else DEFAULT_LOG_LEVEL


@dataclass(frozen=True)
class AppConfig:
    name: str
    version: str
    title: str
    data_dir: Path
    runtime_dir: Path
    log_dir: Path
    log_file: Path
    log_level: str
    min_width: int = 1200
    min_height: int = 800
    width: int = 1280
    height: int = 860
    chrome_frame_min_height: int = 620
    resize_interval_ms: int = 500
    taskbar_flash_guard_interval_ms: int = 500
    log_drawer_collapsed_height: int = 28
    log_drawer_expanded_height: int = 170
    log_drawer_animation_ms: int = 180


@dataclass(frozen=True)
class BrowserConfig:
    profile_dir: Path
    driver_path_cache_file: Path
    driver_cache_valid_days: int = 7
    hidden_window_position: tuple[int, int] = (-10000, -10000)
    initial_window_size: tuple[int, int] = (1280, 800)
    hwnd_lookup_timeout_seconds: float = 10.0
    headless: bool = False
    captcha_api_key: str = ""


def build_app_config(env: Mapping[str, str] | None = None) -> AppConfig:
    data_dir = resolve_app_data_dir(env)
    runtime_dir = data_dir / "runtime"
    log_dir = data_dir / "logs"

    return AppConfig(
        name=APP_NAME,
        version=APP_VERSION,
        title=APP_NAME,
        data_dir=data_dir,
        runtime_dir=runtime_dir,
        log_dir=log_dir,
        log_file=log_dir / "autobrowser.log",
        log_level=resolve_log_level(env),
    )


def build_browser_config(
    app_config: AppConfig | None = None,
    env: Mapping[str, str] | None = None,
) -> BrowserConfig:
    if app_config is None:
        app_config = build_app_config(env)

    profile_dir = _resolve_profile_dir(app_config.data_dir)

    return BrowserConfig(
        profile_dir=profile_dir,
        driver_path_cache_file=app_config.runtime_dir / "chromedriver_path.txt",
        headless=_resolve_headless(app_config.data_dir),
    )


def _resolve_profile_dir(data_dir: Path) -> Path:
    try:
        from autobrowser.browser.profile_manager import get_active_profile_dir
        return get_active_profile_dir(data_dir)
    except Exception:
        return data_dir / "chrome_profile"


def _resolve_headless(data_dir: Path) -> bool:
    try:
        from autobrowser.app_settings import load_settings
        return load_settings(data_dir).headless
    except Exception:
        return False


load_dotenv_file()

APP_CONFIG = build_app_config()
BROWSER_CONFIG = build_browser_config(APP_CONFIG)
