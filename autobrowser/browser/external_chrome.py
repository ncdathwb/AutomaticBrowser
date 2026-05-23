import os
import shutil
import subprocess
from pathlib import Path

from autobrowser.browser.profile import prepare_profile
from autobrowser.config import BROWSER_CONFIG, BrowserConfig


def launch_external_chrome(
    url: str,
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
            url,
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
