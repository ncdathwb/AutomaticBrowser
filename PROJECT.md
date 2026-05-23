# AutoBrowser Architecture Notes

## Overview

AutoBrowser is a Windows desktop app built with PyQt5 and Selenium. It starts Chrome with a dedicated app profile, embeds the Chrome window into the PyQt UI, then runs the current automation workflow: open the BHXC site and submit the login form.

The architecture keeps UI, orchestration, browser automation, and Win32 integration separated so the app can be tested and packaged without mixing responsibilities.

## Main Structure

- `main.py`: thin entrypoint for `python main.py`.
- `autobrowser/app.py`: configures logging, creates `QApplication`, and opens the main window.
- `autobrowser/config.py`: app metadata, AppData paths, runtime paths, and env overrides.
- `autobrowser/ui/`: PyQt widgets and styles.
- `autobrowser/controllers/browser_controller.py`: threads, timers, browser lifecycle, navigation state, and external login fallback.
- `autobrowser/browser/`: Selenium session, BHXC automation, external Chrome fallback, and Chrome profile cleanup.
- `autobrowser/browser/actions/`: reusable Selenium helpers for clicks, typing, waits, and action chains.
- `autobrowser/platform/win32_window.py`: Windows HWND embedding, resize, focus, release, and taskbar behavior.
- `tests/`: unit tests for pure logic.

## Runtime Flow

1. `python main.py` calls `autobrowser.app.main()`.
2. `app.main()` configures rotating file logging under `%LOCALAPPDATA%\AutoBrowser\logs`.
3. The UI creates `AutoBrowserWindow`, then starts `BrowserController`.
4. The controller prepares the app Chrome profile, starts Selenium Chrome, finds the Chrome HWND, and requests UI embedding.
5. After embedding, the controller runs the BHXC login workflow.
6. If the site detects Selenium after form submission, the UI shows `Đăng nhập ngoài` to open real Chrome with the same app profile.

## Production Runtime Data

- Default data dir: `%LOCALAPPDATA%\AutoBrowser`
- Chrome profile: `%LOCALAPPDATA%\AutoBrowser\chrome_profile`
- Runtime cache: `%LOCALAPPDATA%\AutoBrowser\runtime`
- Log file: `%LOCALAPPDATA%\AutoBrowser\logs\autobrowser.log`

Environment overrides:

- `AUTOBROWSER_DATA_DIR`: override the whole app data directory.
- `AUTOBROWSER_LOG_LEVEL`: override log level. Default: `INFO`.
- `AUTOBROWSER_LOGIN_ACCOUNT`: account value typed into the BHXC login form.
- `AUTOBROWSER_LOGIN_PASSWORD`: password value typed into the BHXC login form.

The old repo-local `chrome_profile/` is not migrated automatically. To keep an existing login, copy it manually to `%LOCALAPPDATA%\AutoBrowser\chrome_profile` before first production run.

## Development

```powershell
python -m pip install -r requirements.txt
python main.py
```

Full quality gate:

```powershell
python -m pip install -r requirements-dev.txt
.\scripts\check.ps1
```

## Changing Automation Workflow

Edit only `autobrowser/browser/automation.py` when changing what the browser does after startup. Keep `run_browser_logic(session) -> str` as the controller entrypoint, keep Selenium operations inside `with session.lock`, import reusable helpers from `autobrowser/browser/actions/`, and return the final `driver.current_url`.

## Production Build

Use Python 3.12 in a virtual environment:

```powershell
python -m pip install -r requirements-dev.txt
.\scripts\build_windows.ps1
```

Outputs:

- `dist\AutoBrowser\AutoBrowser.exe`
- `dist\AutoBrowser-0.1.0-win64.zip`

Google Chrome is not bundled; the target machine must already have Chrome installed.

## Manual Smoke Test

- App opens maximized.
- Chrome embeds into the browser frame.
- BHXC login form opens.
- If credentials are configured, the account and password are typed and submitted.
- If credentials are missing, the app leaves the login form open and logs which environment variables to fill.
- Window resize does not detach or misalign Chrome.
- Log file is created in AppData.
- Closing and reopening the app reuses the same AppData profile.
- No `.runtime/` or `chrome_profile/` folder is created beside the release executable.

## Troubleshooting

- Chrome HWND not found: confirm Chrome opened through Selenium and still uses class `Chrome_WidgetWin_1`.
- Selenium login rejected: click `Đăng nhập ngoài`, log in with real Chrome, close external Chrome, and restart the app.
- Profile locked: the app closes Chrome processes using the app profile, removes stale lock files, and marks the profile clean before opening Selenium.
