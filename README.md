# AutoBrowser

AutoBrowser is a Windows desktop app built with PyQt5 and Selenium. It starts Chrome with a dedicated local profile, embeds the Chrome window inside the PyQt interface, and runs the current automation workflow: open the BHXC site and submit the login form.

## Requirements

- Windows
- Google Chrome
- Python 3.11 or newer for development
- Python 3.12 for production builds

## Setup

```powershell
python -m pip install -r requirements.txt
```

For production tooling:

```powershell
python -m pip install -r requirements-dev.txt
```

## Run

```powershell
python main.py
```

## Test

```powershell
python -m unittest discover -s tests
```

Full quality gate:

```powershell
.\scripts\check.ps1
```

## Build

Use Python 3.12 in a virtual environment, then run:

```powershell
.\scripts\build_windows.ps1
```

The build output is:

- `dist\AutoBrowser\AutoBrowser.exe`
- `dist\AutoBrowser-0.1.0-win64.zip`

Google Chrome is not bundled. The target machine must already have Chrome installed.

## Configuration

Runtime data is stored outside the repo by default:

- `%LOCALAPPDATA%\AutoBrowser\chrome_profile`
- `%LOCALAPPDATA%\AutoBrowser\runtime`
- `%LOCALAPPDATA%\AutoBrowser\logs\autobrowser.log`

Environment overrides:

- `AUTOBROWSER_DATA_DIR`: override the app data directory.
- `AUTOBROWSER_LOG_LEVEL`: override logging level. Default: `INFO`.
- `AUTOBROWSER_LOGIN_ACCOUNT`: account value typed into the BHXC login form.
- `AUTOBROWSER_LOGIN_PASSWORD`: password value typed into the BHXC login form.

The old development `chrome_profile/` folder is not migrated automatically. To keep an existing login, close Chrome and copy `chrome_profile/` to `%LOCALAPPDATA%\AutoBrowser\chrome_profile` before starting the packaged app.

If BHXC rejects or detects Selenium-driven login, the `Đăng nhập ngoài` button appears in the log bar. Use it to open real Chrome with the same app profile, log in manually, close that Chrome window, then restart AutoBrowser.

## Project Layout

- `main.py`: thin application entrypoint.
- `autobrowser/app.py`: creates the Qt application and main window.
- `autobrowser/config.py`: app and browser runtime settings.
- `autobrowser/ui/`: PyQt window and styles.
- `autobrowser/controllers/`: UI-to-browser orchestration, timers, threads, and state.
- `autobrowser/browser/`: Selenium session, BHXC automation, external Chrome fallback, and Chrome profile handling.
- `autobrowser/browser/actions/`: reusable Selenium helpers for clicks, typing, waits, and action chains.
- `autobrowser/platform/`: Windows-specific HWND embedding, resize, focus, and taskbar behavior.
- `tests/`: unit tests for pure logic.

## Changing Automation

To replace the current BHXC login workflow, edit `autobrowser/browser/automation.py` only. Keep `run_browser_logic(session) -> str` as the stable entrypoint and return the final browser URL. Import reusable click, typing, wait, and action-chain helpers from `autobrowser/browser/actions/`.

## Runtime Data

- `chrome_profile/` was the old development profile location and is ignored by git.
- `.runtime/` was the old development runtime cache and is ignored by git.
- Production runtime data lives in `%LOCALAPPDATA%\AutoBrowser` unless overridden.

Both directories are ignored by git.

See `PROJECT.md` for a deeper architecture note and troubleshooting guide.
