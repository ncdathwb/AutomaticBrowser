from dataclasses import dataclass
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
RUNTIME_DIR = BASE_DIR / ".runtime"


@dataclass(frozen=True)
class AppConfig:
    title: str = "Autommactic Browser"
    min_width: int = 1200
    min_height: int = 800
    width: int = 1280
    height: int = 860
    chrome_frame_min_height: int = 620
    resize_interval_ms: int = 500
    log_drawer_collapsed_height: int = 28
    log_drawer_expanded_height: int = 170
    log_drawer_animation_ms: int = 180


@dataclass(frozen=True)
class BrowserConfig:
    start_url: str = "https://www.google.com/"
    google_login_url: str = "https://accounts.google.com/"
    profile_dir: Path = BASE_DIR / "chrome_profile"
    driver_path_cache_file: Path = RUNTIME_DIR / "chromedriver_path.txt"
    hidden_window_position: tuple[int, int] = (-10000, -10000)
    initial_window_size: tuple[int, int] = (1280, 800)
    hwnd_lookup_timeout_seconds: float = 10.0
    driver_cache_valid_days: int = 365


APP_CONFIG = AppConfig()
BROWSER_CONFIG = BrowserConfig()
