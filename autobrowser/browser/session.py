import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import psutil
import win32gui
import win32process
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.driver_cache import DriverCacheManager

from autobrowser.browser.profile import prepare_profile
from autobrowser.config import BROWSER_CONFIG, BrowserConfig
from autobrowser.proxy_config import build_proxy_arg, load_proxy_config

logger = logging.getLogger(__name__)


CHROME_LANGUAGE = "vi-VN"
CHROME_ACCEPT_LANGUAGES = "vi-VN,vi,en-US,en"


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


@dataclass
class BrowserSession:
    driver: webdriver.Chrome
    hwnd: int | None
    lock: Any = field(default_factory=threading.RLock, repr=False)


def create_browser_session(config: BrowserConfig = BROWSER_CONFIG) -> BrowserSession:
    profile_path = config.profile_dir
    closed_count = prepare_profile(profile_path)
    if closed_count:
        logger.info(
            "Đã đóng %s tiến trình Chrome đang dùng hồ sơ trình duyệt của ứng dụng",
            closed_count,
        )

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
        logger.exception("Không tạo được phiên trình duyệt")
        if driver:
            driver.quit()
        raise


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
    options.add_argument(f"--lang={CHROME_LANGUAGE}")
    options.add_experimental_option(
        "prefs",
        {
            "intl.accept_languages": CHROME_ACCEPT_LANGUAGES,
            "profile.exit_type": "Normal",
            "profile.exited_cleanly": True,
            "session.restore_on_startup": 5,
        },
    )
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--webrtc-ip-handling-policy=disable_non_proxied_udp")

    proxy_config = load_proxy_config(config.profile_dir.parent)
    proxy_arg = build_proxy_arg(proxy_config)
    if proxy_arg:
        options.add_argument(proxy_arg)
        if proxy_config.username:
            options.add_argument(
                f"--proxy-auth={proxy_config.username}:{proxy_config.password}"
            )

    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    return options


def _inject_stealth_scripts(driver: webdriver.Chrome) -> None:
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {
            "source": """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});

// --- navigator.plugins (PluginArray / Plugin mimicry) ---
(function() {
    var _originalPlugins = navigator.plugins;
    if (_originalPlugins && _originalPlugins.length > 0) return;

    var PluginProto = (typeof Plugin !== 'undefined') ? Plugin.prototype : null;
    var PluginArrayProto = (typeof PluginArray !== 'undefined') ? PluginArray.prototype : null;

    function _makeFakePlugin(name, filename, description, mimeCount) {
        var plugin = PluginProto ? Object.create(PluginProto) : {};
        Object.defineProperties(plugin, {
            name:        { value: name, enumerable: true },
            filename:    { value: filename, enumerable: true },
            description: { value: description, enumerable: true },
            length:      { value: mimeCount, enumerable: true },
        });
        if (!PluginProto && typeof Symbol !== 'undefined' && Symbol.toStringTag) {
            Object.defineProperty(plugin, Symbol.toStringTag, { value: 'Plugin' });
        }
        plugin.namedItem = function() { return null; };
        plugin.item = function(i) { return null; };
        return plugin;
    }

    var _fakePlugins = PluginArrayProto ? Object.create(PluginArrayProto) : [];
    var _data = [
        _makeFakePlugin('Chrome PDF Plugin', 'internal-pdf-viewer',
                        'Portable Document Format', 1),
        _makeFakePlugin('Chrome PDF Viewer',
                        'mhjfbmdgcfjbbpaeojofohoefgiehjai', '', 1),
        _makeFakePlugin('Native Client', 'internal-nacl-plugin', '', 2),
    ];
    for (var i = 0; i < _data.length; i++) {
        Object.defineProperty(_fakePlugins, i, {
            value: _data[i], enumerable: true, writable: false, configurable: true
        });
    }
    Object.defineProperty(_fakePlugins, 'length', {
        value: _data.length, enumerable: false
    });
    if (typeof Symbol !== 'undefined' && Symbol.toStringTag) {
        Object.defineProperty(_fakePlugins, Symbol.toStringTag, {
            value: 'PluginArray'
        });
    }
    _fakePlugins.item = function(i) { return _data[i] || null; };
    _fakePlugins.namedItem = function(n) {
        for (var k = 0; k < _data.length; k++) {
            if (_data[k].name === n) return _data[k];
        }
        return null;
    };
    _fakePlugins.refresh = function() {};

    Object.defineProperty(navigator, 'plugins', {
        get: function() { return _fakePlugins; },
        enumerable: true, configurable: true,
    });
})();

// --- navigator.mimeTypes (complement to plugins) ---
(function() {
    var _originalMimeTypes = navigator.mimeTypes;
    if (_originalMimeTypes && _originalMimeTypes.length > 0) return;

    var MimeTypeProto = (typeof MimeType !== 'undefined') ? MimeType.prototype : null;
    var MimeTypeArrayProto = (typeof MimeTypeArray !== 'undefined') ? MimeTypeArray.prototype : null;

    var _mimeData = [
        {type: 'application/pdf', suffixes: 'pdf',
         description: 'Portable Document Format'},
        {type: 'text/pdf', suffixes: 'pdf', description: ''},
    ];
    var _fakeMimeTypes = MimeTypeArrayProto ? Object.create(MimeTypeArrayProto) : [];
    var _mtObjects = [];
    for (var j = 0; j < _mimeData.length; j++) {
        var mt = MimeTypeProto ? Object.create(MimeTypeProto) : {};
        Object.defineProperties(mt, {
            type:        { value: _mimeData[j].type, enumerable: true },
            suffixes:    { value: _mimeData[j].suffixes, enumerable: true },
            description: { value: _mimeData[j].description, enumerable: true },
        });
        if (!MimeTypeProto && typeof Symbol !== 'undefined' && Symbol.toStringTag) {
            Object.defineProperty(mt, Symbol.toStringTag, { value: 'MimeType' });
        }
        _mtObjects.push(mt);
        Object.defineProperty(_fakeMimeTypes, j, {
            value: mt, enumerable: true, writable: false, configurable: true
        });
    }
    Object.defineProperty(_fakeMimeTypes, 'length', {
        value: _mimeData.length, enumerable: false
    });
    if (typeof Symbol !== 'undefined' && Symbol.toStringTag) {
        Object.defineProperty(_fakeMimeTypes, Symbol.toStringTag, {
            value: 'MimeTypeArray'
        });
    }
    _fakeMimeTypes.item = function(i) { return _mtObjects[i] || null; };
    _fakeMimeTypes.namedItem = function(n) {
        for (var m = 0; m < _mtObjects.length; m++) {
            if (_mtObjects[m].type === n) return _mtObjects[m];
        }
        return null;
    };

    Object.defineProperty(navigator, 'mimeTypes', {
        get: function() { return _fakeMimeTypes; },
        enumerable: true, configurable: true,
    });
})();

// --- navigator.language / navigator.languages (DOMStringList mimicry) ---
(function() {
    var _languages = ['vi-VN', 'vi', 'en-US', 'en'];
    Object.defineProperty(navigator, 'language', {get: function() { return 'vi-VN'; }});

    function _createFakeDOMStringList(arr) {
        var DOMStringListProto = (typeof DOMStringList !== 'undefined') ? DOMStringList.prototype : null;
        var obj = DOMStringListProto ? Object.create(DOMStringListProto) : {};
        Object.defineProperty(obj, 'length', { get: function() { return arr.length; } });
        if (typeof Symbol !== 'undefined' && Symbol.toStringTag) {
            Object.defineProperty(obj, Symbol.toStringTag, { value: 'DOMStringList' });
        }
        for (var i = 0; i < arr.length; i++) {
            (function(idx) {
                Object.defineProperty(obj, idx, {
                    get: function() { return arr[idx]; },
                    enumerable: true,
                });
            })(i);
        }
        obj.item = function(i) { return arr[i] || null; };
        obj.contains = function(s) { return arr.indexOf(s) !== -1; };
        if (typeof Symbol !== 'undefined' && Symbol.iterator) {
            obj[Symbol.iterator] = function() {
                var i = 0;
                var a = arr;
                return {
                    next: function() {
                        if (i < a.length) {
                            return { value: a[i++], done: false };
                        }
                        return { done: true };
                    }
                };
            };
        }
        return obj;
    }

    Object.defineProperty(navigator, 'languages', {
        get: function() { return _createFakeDOMStringList(_languages); },
        enumerable: true, configurable: true,
    });
})();

if (!window.chrome) {
    window.chrome = {runtime: {}, loadTimes: function() {}, csi: function() {}, app: {}};
}

if (!window.chrome.runtime) {
    window.chrome.runtime = {};
}

var _originalQuery = navigator.permissions.query;
if (_originalQuery) {
    navigator.permissions.query = function(parameters) {
        return parameters.name === 'notifications'
            ? Promise.resolve({state: Notification.permission})
            : _originalQuery(parameters);
    };
}
""",
        },
    )


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
        driver = webdriver.Chrome(
            service=Service(get_chromedriver_path(config)),
            options=build_chrome_options(config),
        )
        _inject_stealth_scripts(driver)
        return driver
    except WebDriverException:
        logger.warning("ChromeDriver trong bộ nhớ đệm bị lỗi; đang tải lại", exc_info=True)
        clear_cached_driver_path(config.driver_path_cache_file)
        driver = webdriver.Chrome(
            service=Service(get_chromedriver_path(config)),
            options=build_chrome_options(config),
        )
        _inject_stealth_scripts(driver)
        return driver


def read_cached_driver_path(cache_file: Path) -> Path | None:
    try:
        driver_path = Path(cache_file.read_text(encoding="utf-8").strip())
    except OSError:
        return None

    if driver_path.is_file() and "chromedriver" in driver_path.name.lower():
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
