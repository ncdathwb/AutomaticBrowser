import os
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urlparse

import psutil
import win32gui
import win32process
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.driver_cache import DriverCacheManager

from app_config import BROWSER_CONFIG, BrowserConfig
from profile_state import prepare_profile


SKIP_WINDOW_URL_PREFIXES = (
    "chrome-extension://",
    "chrome://omnibox-popup",
    "chrome-untrusted://",
    "devtools://",
)

PREFERRED_BLANK_WINDOW_URL_PREFIXES = (
    "about:blank",
    "chrome://new-tab-page",
    "chrome://newtab",
    "data:,",
)

YOUTUBE_URL = "https://www.youtube.com/"
YOUTUBE_SEARCH_QUERY = "việt nam"
YOUTUBE_SEARCH_TIMEOUT_SECONDS = 12.0

GOOGLE_AUTH_COOKIE_NAMES = {
    "SID",
    "HSID",
    "SSID",
    "APISID",
    "SAPISID",
    "LSID",
    "__Secure-1PSID",
    "__Secure-3PSID",
}


@dataclass
class BrowserSession:
    driver: webdriver.Chrome
    hwnd: int | None
    lock: Any = field(default_factory=threading.RLock, repr=False)


def create_browser_session(config: BrowserConfig = BROWSER_CONFIG) -> BrowserSession:
    profile_path = config.profile_dir
    prepare_profile(profile_path)

    driver = None
    try:
        driver = start_webdriver(config)
        select_live_browser_window(driver)

        chrome_pid = driver.service.process.pid
        hwnd = find_chrome_hwnd_for_process_tree(
            chrome_pid,
            timeout=config.hwnd_lookup_timeout_seconds,
        )

        return BrowserSession(
            driver=driver,
            hwnd=hwnd,
        )
    except Exception:
        if driver:
            driver.quit()
        raise


def navigate_to(session: BrowserSession, url: str) -> str:
    target_url = normalize_url(url)
    with session.lock:
        select_live_browser_window(session.driver)
        session.driver.get(target_url)
        select_live_browser_window(session.driver)
        return session.driver.current_url


def run_browser_logic(session: BrowserSession) -> str:
    return search_youtube(session)


def search_youtube(
    session: BrowserSession,
    query: str = YOUTUBE_SEARCH_QUERY,
) -> str:
    with session.lock:
        driver = session.driver
        select_live_browser_window(driver)
        driver.get(YOUTUBE_URL)

        try:
            search_box = WebDriverWait(
                driver,
                YOUTUBE_SEARCH_TIMEOUT_SECONDS,
            ).until(EC.element_to_be_clickable((By.NAME, "search_query")))
            search_box.clear()
            search_box.send_keys(query)
            search_box.send_keys(Keys.ENTER)
            WebDriverWait(
                driver,
                YOUTUBE_SEARCH_TIMEOUT_SECONDS,
            ).until(is_youtube_search_results_page)
        except (TimeoutException, WebDriverException):
            driver.get(build_youtube_search_url(query, YOUTUBE_URL))

        select_live_browser_window(driver)
        return driver.current_url


def is_youtube_search_results_page(driver: webdriver.Chrome) -> bool:
    current_url = driver.current_url
    parsed = urlparse(current_url)
    return parsed.path.startswith("/results") and "search_query=" in parsed.query


def build_youtube_search_url(query: str, youtube_url: str) -> str:
    return f"{youtube_url.rstrip('/')}/results?search_query={quote_plus(query)}"


def get_current_url(session: BrowserSession) -> str:
    with session.lock:
        select_live_browser_window(session.driver)
        return session.driver.current_url


def select_live_browser_window(driver: webdriver.Chrome) -> str:
    fallback_handle = None
    last_error = None

    for handle in driver.window_handles:
        try:
            driver.switch_to.window(handle)
            current_url = driver.current_url
        except WebDriverException as e:
            last_error = e
            continue

        if current_url.startswith(SKIP_WINDOW_URL_PREFIXES):
            continue

        if current_url.startswith(PREFERRED_BLANK_WINDOW_URL_PREFIXES):
            fallback_handle = handle
            continue

        return handle

    if fallback_handle:
        driver.switch_to.window(fallback_handle)
        return fallback_handle

    if last_error:
        raise last_error

    raise WebDriverException("Không tìm thấy tab Chrome còn hoạt động.")


def build_chrome_options(config: BrowserConfig) -> Options:
    x, y = config.hidden_window_position
    width, height = config.initial_window_size

    options = Options()
    options.add_argument(f"--user-data-dir={config.profile_dir}")
    options.add_argument(f"--window-position={x},{y}")
    options.add_argument(f"--window-size={width},{height}")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--disable-session-crashed-bubble")
    options.add_argument("--hide-crash-restore-bubble")
    options.add_experimental_option(
        "prefs",
        {
            "profile.exit_type": "Normal",
            "profile.exited_cleanly": True,
            "session.restore_on_startup": 5,
        },
    )
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    return options


def get_chromedriver_path(config: BrowserConfig) -> str:
    cached_path = read_cached_driver_path(config.driver_path_cache_file)
    if cached_path:
        return str(cached_path)

    cache_manager = DriverCacheManager(valid_range=config.driver_cache_valid_days)
    driver_path = Path(ChromeDriverManager(cache_manager=cache_manager).install())
    write_cached_driver_path(config.driver_path_cache_file, driver_path)
    return str(driver_path)


def start_webdriver(config: BrowserConfig) -> webdriver.Chrome:
    try:
        return webdriver.Chrome(
            service=Service(get_chromedriver_path(config)),
            options=build_chrome_options(config),
        )
    except WebDriverException:
        clear_cached_driver_path(config.driver_path_cache_file)
        return webdriver.Chrome(
            service=Service(get_chromedriver_path(config)),
            options=build_chrome_options(config),
        )


def read_cached_driver_path(cache_file: Path) -> Path | None:
    try:
        driver_path = Path(cache_file.read_text(encoding="utf-8").strip())
    except OSError:
        return None

    if driver_path.is_file():
        return driver_path
    return None


def write_cached_driver_path(cache_file: Path, driver_path: Path) -> None:
    try:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(str(driver_path), encoding="utf-8")
    except OSError:
        pass


def clear_cached_driver_path(cache_file: Path) -> None:
    try:
        cache_file.unlink(missing_ok=True)
    except OSError:
        pass


def normalize_url(url: str) -> str:
    clean_url = url.strip()
    if clean_url.startswith(("http://", "https://")):
        return clean_url
    return f"https://{clean_url}"


def is_google_captcha_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.netloc.endswith("google.com") and parsed.path.startswith("/sorry")


def is_google_login_rejected_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.netloc.endswith("google.com") and "/signin/rejected" in parsed.path


def has_google_login_session(session: BrowserSession) -> bool:
    try:
        with session.lock:
            select_live_browser_window(session.driver)
            cookies = session.driver.get_cookies()
    except Exception:
        return False

    for cookie in cookies:
        domain = cookie.get("domain", "")
        name = cookie.get("name", "")
        if domain.endswith("google.com") and name in GOOGLE_AUTH_COOKIE_NAMES:
            return True

    return False


def launch_external_chrome_for_login(
    config: BrowserConfig = BROWSER_CONFIG,
) -> subprocess.Popen:
    chrome_path = find_chrome_executable()
    if not chrome_path:
        raise FileNotFoundError("Không tìm thấy Google Chrome trên máy.")

    prepare_profile(config.profile_dir)
    return subprocess.Popen(
        [
            str(chrome_path),
            f"--user-data-dir={config.profile_dir}",
            "--no-first-run",
            "--new-window",
            config.google_login_url,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def find_chrome_executable() -> Path | None:
    path_from_env = shutil.which("chrome") or shutil.which("chrome.exe")
    if path_from_env:
        return Path(path_from_env)

    local_app_data = os.environ.get("LOCALAPPDATA")
    candidates = [
        Path(os.environ.get("PROGRAMFILES", "")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Google/Chrome/Application/chrome.exe",
    ]

    if local_app_data:
        candidates.append(Path(local_app_data) / "Google/Chrome/Application/chrome.exe")

    for candidate in candidates:
        if candidate.is_file():
            return candidate

    return None


def find_chrome_hwnd_for_process_tree(
    root_pid: int,
    timeout: float,
) -> int | None:
    start = time.time()
    while time.time() - start < timeout:
        pids = set(get_process_tree_pids(root_pid))
        hwnd = find_chrome_hwnd_for_pids(pids)
        if hwnd:
            return hwnd
        time.sleep(0.2)
    return None


def get_process_tree_pids(parent_pid: int) -> list[int]:
    pids = [parent_pid]
    try:
        parent = psutil.Process(parent_pid)
        for child in parent.children(recursive=True):
            pids.append(child.pid)
    except psutil.NoSuchProcess:
        pass
    return pids


def find_chrome_hwnd_for_pids(pids: set[int]) -> int | None:
    found_hwnd = []

    def enum_callback(hwnd, _):
        if found_hwnd:
            return
        if not win32gui.IsWindowVisible(hwnd):
            return
        if not win32gui.GetWindowText(hwnd):
            return

        _, window_pid = win32process.GetWindowThreadProcessId(hwnd)
        class_name = win32gui.GetClassName(hwnd)
        if window_pid in pids and class_name == "Chrome_WidgetWin_1":
            found_hwnd.append(hwnd)

    win32gui.EnumWindows(enum_callback, None)
    return found_hwnd[0] if found_hwnd else None
