import datetime
import ipaddress
import json
import logging
import os
import random
import time
from pathlib import Path

from selenium.common.exceptions import WebDriverException
from selenium.webdriver.remote.webdriver import WebDriver

from autobrowser.browser.actions.elements import by_id, click
from autobrowser.browser.actions.keyboard import type_text_human
from autobrowser.browser.actions.waits import wait_until, wait_visible
from autobrowser.browser.session import BrowserSession, select_live_browser_window

logger = logging.getLogger(__name__)

TARGET_URL = "https://www.bhxc969.net/Home/Index"
GOOGLE_URL = "https://www.google.com"
PAGE_LOAD_TIMEOUT_SECONDS = 30.0
LOGIN_BUTTON_TIMEOUT_SECONDS = 15.0
LOGIN_FORM_TIMEOUT_SECONDS = 15.0
LOGIN_TYPING_KEY_DELAY_SECONDS = (0.07, 0.2)
LOGIN_TYPING_PAUSE_SECONDS = (0.25, 0.8)
LOGIN_TYPING_PAUSE_CHANCE = 0.14
THINKING_PAUSE_RANGE = (0.3, 1.2)
QR_POLL_INTERVAL_SECONDS = 2.0
QR_MAX_WAIT_SECONDS = 100.0
QR_REFRESH_RETRY_LIMIT: int | None = None
QR_APPEAR_TIMEOUT_SECONDS = 30.0
QR_APPEAR_POLL_SECONDS = 0.5
QR_PASSKEY_KEYWORDS = (
    "passkey", "passkeys", "mã qr", "qr code", "quét mã",
    "scan qr", "authenticator", "xác thực hai lớp",
)
QR_TIMEOUT_KEYWORDS = (
    "something went wrong", "request time out", "request timeout",
    "the request timed out", "hết thời gian", "quá thời gian",
    "time out", "timed out", "expired", "expire", "error occurred",
)
QR_VERIFY_URL_KEYWORDS = ("loginverify", "verify")
NETWORK_INFO_TIMEOUT_MS = 5000

LOGIN_ACCOUNT_ENV = "AUTOBROWSER_LOGIN_ACCOUNT"
LOGIN_PASSWORD_ENV = "AUTOBROWSER_LOGIN_PASSWORD"


def _get_login_account() -> str:
    return os.environ.get(LOGIN_ACCOUNT_ENV, "").strip()


def _get_login_password() -> str:
    return os.environ.get(LOGIN_PASSWORD_ENV, "")


LOGIN_BUTTON_LOCATOR = by_id("loginbutton")
LOGIN_FORM_LOCATOR = by_id("frmLogin")
ACCOUNT_INPUT_LOCATOR = by_id("accountId")
PASSWORD_INPUT_LOCATOR = by_id("accountPwd")
SIGNIN_BUTTON_LOCATOR = by_id("signin")


class ExternalLoginRequired(RuntimeError):
    def __init__(self, url: str, message: str):
        super().__init__(message)
        self.url = url
        self.message = message


def run_browser_logic(
    session: BrowserSession,
    data_dir: Path | None = None,
) -> str:
    return open_target_site(session, data_dir=data_dir)


def open_target_site(
    session: BrowserSession,
    url: str = TARGET_URL,
    data_dir: Path | None = None,
) -> str:
    with session.lock:
        driver = session.driver

        logger.info("Chọn tab trình duyệt đang hoạt động")
        select_live_browser_window(driver)

        logger.info("Mở Google trước để thu thập fingerprint...")
        driver.get(GOOGLE_URL)
        wait_for_dom_complete(driver)
        log_browser_fingerprint(driver, data_dir=data_dir)

        logger.info("Mở trang: %s", url)
        driver.get(url)
        wait_for_dom_complete(driver)

        logger.info("Mở form đăng nhập")
        click_login_button(driver)

        logger.info("Chờ form đăng nhập xuất hiện")
        wait_for_login_form(driver)

        logger.info("Nhập tài khoản và mật khẩu")
        credentials_entered = type_login_credentials(driver, _get_login_account(), _get_login_password())
        if not credentials_entered:
            select_live_browser_window(driver)
            return driver.current_url

        logger.info("Bấm nút đăng nhập")
        time.sleep(random.Random().uniform(*THINKING_PAUSE_RANGE))
        submit_login_form(driver)

        wait_for_qr_scan(driver)

        if is_webdriver_detected(driver):
            message = (
                "Trang phát hiện Chrome đang chạy bằng Selenium và có thể "
                "báo giả là tài khoản hoặc mật khẩu sai. Hãy đăng nhập "
                "bằng Chrome thật dùng cùng hồ sơ trình duyệt của ứng dụng."
            )
            logger.warning(message)
            raise ExternalLoginRequired(url, message)

        logger.info("Đã gửi yêu cầu đăng nhập")
        select_live_browser_window(driver)
        return driver.current_url


def wait_for_dom_complete(
    driver: WebDriver,
    timeout: float = PAGE_LOAD_TIMEOUT_SECONDS,
) -> None:
    if not isinstance(driver, WebDriver):
        return

    wait_until(driver, is_dom_complete, timeout)


def is_dom_complete(driver: WebDriver) -> bool:
    return driver.execute_script("return document.readyState") == "complete"


def click_login_button(
    driver: WebDriver,
    timeout: float = LOGIN_BUTTON_TIMEOUT_SECONDS,
) -> None:
    if not isinstance(driver, WebDriver):
        return

    click(driver, LOGIN_BUTTON_LOCATOR, timeout)


def wait_for_login_form(
    driver: WebDriver,
    timeout: float = LOGIN_FORM_TIMEOUT_SECONDS,
) -> None:
    if not isinstance(driver, WebDriver):
        return

    wait_visible(driver, LOGIN_FORM_LOCATOR, timeout)


def submit_login_form(
    driver: WebDriver,
    timeout: float = LOGIN_FORM_TIMEOUT_SECONDS,
) -> None:
    if not isinstance(driver, WebDriver):
        return

    click(driver, SIGNIN_BUTTON_LOCATOR, timeout)


def is_webdriver_detected(driver: WebDriver) -> bool:
    try:
        return bool(driver.execute_script("return Boolean(window.navigator.webdriver)"))
    except WebDriverException:
        logger.debug("Không thể kiểm tra navigator.webdriver", exc_info=True)
        return False


def type_login_credentials(
    driver: WebDriver,
    account: str,
    password: str,
    timeout: float = LOGIN_FORM_TIMEOUT_SECONDS,
) -> bool:
    if not isinstance(driver, WebDriver):
        return False

    if not account or not password:
        logger.warning(
            "Thiếu tài khoản hoặc mật khẩu. Hãy điền %s và %s để tự động nhập form đăng nhập.",
            LOGIN_ACCOUNT_ENV,
            LOGIN_PASSWORD_ENV,
        )
        return False

    rng = random.Random()

    account_input = click(driver, ACCOUNT_INPUT_LOCATOR, timeout)
    type_text_human(
        account_input,
        account,
        key_delay_seconds=LOGIN_TYPING_KEY_DELAY_SECONDS,
        pause_seconds=LOGIN_TYPING_PAUSE_SECONDS,
        pause_chance=LOGIN_TYPING_PAUSE_CHANCE,
    )
    logger.info("Đã nhập tài khoản")
    time.sleep(rng.uniform(*THINKING_PAUSE_RANGE))

    password_input = click(driver, PASSWORD_INPUT_LOCATOR, timeout)
    type_text_human(
        password_input,
        password,
        key_delay_seconds=LOGIN_TYPING_KEY_DELAY_SECONDS,
        pause_seconds=LOGIN_TYPING_PAUSE_SECONDS,
        pause_chance=LOGIN_TYPING_PAUSE_CHANCE,
    )
    logger.info("Đã nhập mật khẩu")
    time.sleep(rng.uniform(*THINKING_PAUSE_RANGE))
    return True


def _read_all_page_text(driver: WebDriver) -> str:
    try:
        result = driver.execute_script(r"""
            function collectText(root, texts) {
                if (!root) return;
                if (root.body) {
                    texts.push(root.body.textContent || '');
                    texts.push(root.body.innerText || '');
                }

                var walkerRoot = root.body || root;
                var walkerDocument = root.createTreeWalker ? root : document;
                var walker = walkerDocument.createTreeWalker(
                    walkerRoot,
                    NodeFilter.SHOW_ELEMENT
                );
                if (!walker) return;

                var node = walker.currentNode;
                while (node) {
                    if (node.shadowRoot) {
                        texts.push(node.shadowRoot.textContent || '');
                        collectText(node.shadowRoot, texts);
                    }
                    texts.push(node.getAttribute && (node.getAttribute('aria-label') || ''));
                    texts.push(node.getAttribute && (node.getAttribute('title') || ''));
                    node = walker.nextNode();
                }
            }

            var texts = [];
            collectText(document, texts);

            var iframes = document.querySelectorAll('iframe');
            for (var i = 0; i < iframes.length; i++) {
                try {
                    var doc = iframes[i].contentDocument || iframes[i].contentWindow.document;
                    collectText(doc, texts);
                } catch(e) {}
            }
            return texts.join(' ');
        """)
        return (str(result) if result else "").lower()
    except WebDriverException:
        return ""


def _check_browser_alert(driver: WebDriver) -> str:
    try:
        alert = driver.switch_to.alert
        return (alert.text or "").lower()
    except WebDriverException:
        return ""


def _dismiss_alert(driver: WebDriver) -> None:
    logger.info("Đang cố gắng đóng alert/dialog...")
    try:
        driver.switch_to.alert.accept()
        logger.info("Đã đóng JavaScript alert")
        return
    except WebDriverException:
        logger.debug("Không phải JavaScript alert hoặc không accept được")

    try:
        driver.switch_to.alert.dismiss()
        logger.info("Đã dismiss JavaScript dialog")
        return
    except WebDriverException:
        logger.debug("Không dismiss được alert")

    close_selectors = [
        "//button[contains(text(), 'Close') or contains(text(), 'CLOSE') or contains(text(), 'close')]",
        "//button[contains(@class, 'close') or contains(@class, 'btn-close')]",
        "//button[@aria-label='Close']",
        "//*[@aria-label='Close']",
        "//button[contains(text(), 'OK') or contains(text(), 'ok')]",
        "//button[contains(text(), 'Xác nhận') or contains(text(), 'Đồng ý')]",
    ]

    for selector in close_selectors:
        try:
            btn = driver.find_element("xpath", selector)
            btn.click()
            time.sleep(0.5)
            logger.info("Đã click nút đóng dialog: %s", selector)
            return
        except WebDriverException:
            continue

    try:
        driver.execute_script("""
            var modals = document.querySelectorAll(
                '[role="dialog"], [role="alertdialog"], '
                + '.modal, .popup, .overlay, .toast, '
                + '[class*="dialog"], [class*="modal"], [class*="popup"], '
                + '[class*="alert"], [class*="error"]'
            );
            modals.forEach(function(el) {
                el.style.display = 'none';
                el.remove();
            });
        """)
        logger.info("Đã xóa modal/overlay khỏi DOM")
    except WebDriverException:
        logger.debug("Không thể đóng dialog lỗi", exc_info=True)


def _is_qr_passkeys_present(driver: WebDriver) -> bool:
    body_text = _read_all_page_text(driver)
    alert_text = _check_browser_alert(driver)

    if alert_text:
        for keyword in QR_PASSKEY_KEYWORDS:
            if keyword in alert_text:
                logger.debug("Tìm thấy từ khóa passkey trong alert: '%s'", keyword)
                return True
        logger.debug("Có alert nhưng không có từ khóa passkey: '%s'", alert_text[:100])
        return False

    for keyword in QR_PASSKEY_KEYWORDS:
        if keyword in body_text:
            logger.debug("Tìm thấy từ khóa passkey trong body")
            return True
    return False


def _get_qr_login_state(driver: WebDriver) -> tuple[bool, bool, str]:
    alert_text = _check_browser_alert(driver)
    body_text = _read_all_page_text(driver)
    timeout_element_text = _find_visible_text_by_keywords(driver, QR_TIMEOUT_KEYWORDS)

    timeout_source = alert_text or timeout_element_text or body_text
    has_timeout = any(
        keyword in text
        for text in (alert_text, timeout_element_text, body_text)
        if text
        for keyword in QR_TIMEOUT_KEYWORDS
    )
    has_passkeys = any(
        keyword in text
        for text in (alert_text, body_text)
        if text
        for keyword in QR_PASSKEY_KEYWORDS
    )

    if has_timeout:
        logger.info("PHÁT HIỆN TIMEOUT QR: '%s'", timeout_source[:100])

    return has_passkeys, has_timeout, alert_text


def _is_qr_verification_url(driver: WebDriver) -> bool:
    try:
        current_url = str(driver.current_url or "").lower()
    except WebDriverException:
        return False

    return any(keyword in current_url for keyword in QR_VERIFY_URL_KEYWORDS)


def _get_current_url(driver: WebDriver) -> str:
    try:
        return str(driver.current_url or "")
    except WebDriverException:
        return ""


def _press_escape_for_native_dialog(driver: WebDriver, sleep=time.sleep) -> None:
    try:
        driver.execute_cdp_cmd(
            "Input.dispatchKeyEvent",
            {
                "type": "keyDown",
                "key": "Escape",
                "code": "Escape",
                "windowsVirtualKeyCode": 27,
            },
        )
        driver.execute_cdp_cmd(
            "Input.dispatchKeyEvent",
            {
                "type": "keyUp",
                "key": "Escape",
                "code": "Escape",
                "windowsVirtualKeyCode": 27,
            },
        )
        sleep(0.2)
    except WebDriverException:
        logger.debug("Không gửi được phím Escape để đóng hộp thoại native", exc_info=True)


def _reload_page_for_new_qr(driver: WebDriver, sleep=time.sleep) -> bool:
    current_url = _get_current_url(driver)
    _press_escape_for_native_dialog(driver, sleep=sleep)

    if current_url:
        try:
            logger.info("Tải lại trang QR bằng cách điều hướng lại URL hiện tại")
            driver.get("about:blank")
            sleep(0.2)
            driver.get(current_url)
            wait_for_dom_complete(driver)
            logger.info("Đã tải lại trang QR bằng điều hướng browser")
            return True
        except WebDriverException:
            logger.debug(
                "Không điều hướng lại URL hiện tại được, thử CDP Page.navigate",
                exc_info=True,
            )

        try:
            driver.execute_cdp_cmd("Page.navigate", {"url": current_url})
            wait_for_dom_complete(driver)
            logger.info("Đã tải lại trang QR bằng CDP Page.navigate")
            return True
        except WebDriverException:
            logger.debug("Không reload được bằng CDP Page.navigate", exc_info=True)

    try:
        driver.execute_cdp_cmd("Page.reload", {"ignoreCache": True})
        wait_for_dom_complete(driver)
        logger.info("Đã tải lại trang QR bằng CDP Page.reload")
        return True
    except WebDriverException:
        logger.debug("Không reload được bằng CDP Page.reload, thử driver.refresh()", exc_info=True)

    try:
        driver.refresh()
        wait_for_dom_complete(driver)
        logger.info("Đã tải lại trang QR bằng driver.refresh()")
        return True
    except WebDriverException:
        logger.debug("Không reload được bằng driver.refresh(), thử JavaScript", exc_info=True)

    try:
        driver.execute_script("location.reload(true)")
        wait_for_dom_complete(driver)
        logger.info("Đã tải lại trang QR bằng JavaScript")
        return True
    except WebDriverException:
        logger.exception("Không tải lại được trang")
        return False


def _find_visible_text_by_keywords(driver: WebDriver, keywords: tuple[str, ...]) -> str:
    try:
        script = """
            var keywords = arguments[0];
            var MAX_ELEMENTS = 2000;
            var all = document.querySelectorAll(
                'div, span, p, h1, h2, h3, h4, h5, h6, '
                + 'li, td, th, label, button, a, strong, em, b, i'
            );
            var limit = Math.min(all.length, MAX_ELEMENTS);
            for (var i = 0; i < limit; i++) {
                var el = all[i];
                if (el.offsetParent === null) continue;
                var text = (el.textContent || '').toLowerCase().trim();
                if (text.length < 5) continue;
                for (var k = 0; k < keywords.length; k++) {
                    if (text.indexOf(keywords[k]) !== -1) {
                        return text.substring(0, 500);
                    }
                }
            }
            return '';
        """
        result = driver.execute_script(script, keywords)
        return (str(result) if result else "").lower()
    except WebDriverException:
        return ""


def wait_for_qr_scan(
    driver: WebDriver,
    poll_interval: float = QR_POLL_INTERVAL_SECONDS,
    max_wait: float = QR_MAX_WAIT_SECONDS,
    retry_limit: int | None = QR_REFRESH_RETRY_LIMIT,
    appear_timeout: float = QR_APPEAR_TIMEOUT_SECONDS,
    appear_poll: float = QR_APPEAR_POLL_SECONDS,
    sleep=time.sleep,
) -> None:
    attempt = 1
    while retry_limit is None or attempt <= retry_limit:
        if attempt == 1:
            logger.info(
                "Đang chờ dialog QR/Passkeys xuất hiện (tối đa %.0f giây)...",
                appear_timeout,
            )

        qr_appeared = _wait_for_qr_to_appear(
            driver,
            timeout=appear_timeout,
            poll_seconds=appear_poll,
            sleep=sleep,
        )

        if not qr_appeared:
            if attempt == 1:
                logger.info("Không phát hiện dialog QR/Passkeys, tiếp tục")
            else:
                logger.info("QR/Passkeys không còn hiển thị — đã quét thành công")
            return

        logger.info(
            "Phát hiện dialog QR/Passkeys — đang chờ người dùng quét mã "
            "(lần %d, kiểm tra mỗi %.0f giây, tối đa %.0f giây)...",
            attempt,
            poll_interval,
            max_wait,
        )

        start = time.time()
        poll_count = 0
        prev_alert = None
        prev_passkeys = None
        verify_url_seen = _is_qr_verification_url(driver)
        while time.time() - start < max_wait:
            sleep(poll_interval)
            poll_count += 1

            has_passkeys, has_timeout, alert_text = _get_qr_login_state(driver)
            is_verify_url = _is_qr_verification_url(driver)
            verify_url_seen = verify_url_seen or is_verify_url

            alert_changed = (bool(alert_text) != bool(prev_alert))
            passkeys_changed = (has_passkeys != prev_passkeys)

            if poll_count == 1 or alert_changed or passkeys_changed or has_timeout:
                elapsed = time.time() - start
                if alert_text and len(alert_text) > 80:
                    alert_short = alert_text[:80] + "..."
                else:
                    alert_short = alert_text or "(không có)"
                logger.info(
                    "[Poll #%d | %.0fs] passkeys=%s timeout=%s verify_url=%s alert=%s",
                    poll_count,
                    elapsed,
                    has_passkeys,
                    has_timeout,
                    is_verify_url,
                    alert_short,
                )
            elif poll_count % 15 == 0:
                elapsed = time.time() - start
                logger.info(
                    "Vẫn đang chờ quét QR... (poll #%d, %.0fs)",
                    poll_count,
                    elapsed,
                )

            prev_alert = alert_text
            prev_passkeys = has_passkeys

            if verify_url_seen and not is_verify_url:
                elapsed = time.time() - start
                logger.info(
                    "Đã rời trang xác minh QR/Passkeys sau %.1f giây (lần %d) "
                    "— xem như đã quét thành công",
                    elapsed,
                    attempt,
                )
                return

            if has_timeout:
                logger.warning(
                    "QR/Passkeys đã hết hạn hoặc báo lỗi. Đang đóng dialog và tải lại trang..."
                )
                _dismiss_alert(driver)
                sleep(0.5)
                logger.info("Đang tải lại trang để lấy mã QR mới...")
                break

            if not has_passkeys:
                elapsed = time.time() - start
                logger.info(
                    "Đã quét mã QR/Passkeys thành công sau %.1f giây (lần %d)",
                    elapsed,
                    attempt,
                )
                return

        else:
            logger.warning(
                "Đã chờ QR %.0f giây nhưng chưa quét xong. "
                "Chủ động tải lại trước khi hộp thoại native của Chrome bị kẹt...",
                max_wait,
            )

        if retry_limit is not None and attempt >= retry_limit:
            break

        _reload_page_for_new_qr(driver, sleep=sleep)
        sleep(1.5)
        attempt += 1

    if retry_limit is not None:
        logger.warning(
            "Đã đạt giới hạn %d lần làm mới QR nhưng vẫn chưa quét được",
            retry_limit,
        )


def _wait_for_qr_to_appear(
    driver: WebDriver,
    timeout: float,
    poll_seconds: float,
    sleep=time.sleep,
) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        if _is_qr_passkeys_present(driver):
            return True
        sleep(poll_seconds)
    return False


def log_browser_fingerprint(
    driver: WebDriver,
    data_dir: Path | None = None,
) -> None:
    try:
        info = _collect_sync_fingerprint(driver)
    except WebDriverException:
        logger.debug("Không thể thu thập thông tin trình duyệt", exc_info=True)
        return

    if not isinstance(info, dict):
        logger.warning("Không thu thập được fingerprint — JS trả về kiểu không mong đợi: %s", type(info).__name__)
        return

    logger.info("=== Thông tin trình duyệt ===")
    logger.info("User-Agent : %s", info.get("userAgent", "N/A"))
    logger.info("Platform   : %s", info.get("platform", "N/A"))
    logger.info("Vendor     : %s | productSub: %s",
                info.get("vendor", "N/A"), info.get("productSub", "N/A"))
    logger.info("Ngôn ngữ   : %s (%s)", info.get("language", "N/A"), info.get("languages", "N/A"))
    logger.info("Múi giờ    : %s", info.get("timezone", "N/A"))
    logger.info("Màn hình   : %dx%d (khả dụng: %dx%d) | cửa sổ: %dx%d",
                info.get("screenW", 0), info.get("screenH", 0),
                info.get("screenAvailW", 0), info.get("screenAvailH", 0),
                info.get("windowW", 0), info.get("windowH", 0))
    logger.info("Màu sắc    : colorDepth=%s | pixelDepth=%s",
                info.get("colorDepth", "N/A"), info.get("pixelDepth", "N/A"))
    logger.info("CPU        : %s cores | RAM: %s GB",
                info.get("hardwareConcurrency", "N/A"), info.get("deviceMemory", "N/A"))
    logger.info("Cảm ứng    : %s (maxTouchPoints=%s)",
                "CÓ" if info.get("touchSupport") else "không",
                info.get("maxTouchPoints", "N/A"))

    webdriver_val = info.get("webdriver")
    if webdriver_val is True:
        webdriver_display = "TRUE (bị phát hiện!)"
    elif webdriver_val is None:
        webdriver_display = "không (đã ẩn)"
    else:
        webdriver_display = str(webdriver_val)
    logger.info("WebDriver  : %s", webdriver_display)
    logger.info("DoNotTrack : %s", info.get("doNotTrack", "N/A"))

    logger.info("--- Fingerprint nâng cao ---")
    logger.info("WebGL      : %s | %s", info.get("webglVendor", "N/A"), info.get("webglRenderer", "N/A"))
    logger.info("WebGL ver  : %s | GLSL: %s",
                info.get("webglVersion", "N/A"), info.get("webglShadingVersion", "N/A"))
    logger.info("WebGL caps : tex=%s viewport=%s rb=%s ext=%s",
                info.get("webglMaxTextureSize", "N/A"),
                info.get("webglMaxViewport", "N/A"),
                info.get("webglMaxRbSize", "N/A"),
                info.get("webglExtensions", "N/A"))
    logger.info("Canvas hash: %s", info.get("canvasHash", "N/A"))
    logger.info("Fonts      : %s", info.get("fonts", "N/A"))
    logger.info("Plugins    : %s", info.get("plugins", "N/A"))

    webrtc_result, audio_hash = _collect_async_fingerprint(driver)
    info["audioHash"] = audio_hash

    # Chuyển về about:blank để tránh CSP của Google chặn fetch()
    driver.get("about:blank")
    external_ip, proxy_headers = _collect_browser_network_info(driver)

    _analyze_and_conclude(
        info, webrtc_result, external_ip, proxy_headers, data_dir=data_dir,
    )

    if data_dir:
        _save_fingerprint_json(
            info, webrtc_result, external_ip, proxy_headers, data_dir,
        )


def _collect_sync_fingerprint(driver: WebDriver) -> dict:
    return driver.execute_script(r"""
        var info = {
            userAgent: navigator.userAgent,
            platform: navigator.platform,
            language: navigator.language,
            languages: navigator.languages,
            cookieEnabled: navigator.cookieEnabled,
            hardwareConcurrency: navigator.hardwareConcurrency,
            deviceMemory: navigator.deviceMemory || 'N/A',
            webdriver: navigator.webdriver,
            vendor: navigator.vendor,
            productSub: navigator.productSub,
            screenW: screen.width,
            screenH: screen.height,
            screenAvailW: screen.availWidth,
            screenAvailH: screen.availHeight,
            windowW: window.innerWidth,
            windowH: window.innerHeight,
            colorDepth: screen.colorDepth,
            pixelDepth: screen.pixelDepth,
            maxTouchPoints: navigator.maxTouchPoints || 0,
            touchSupport: ('ontouchstart' in window) || (navigator.maxTouchPoints > 0),
            timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
            doNotTrack: navigator.doNotTrack,
        };

        // Plugins
        try {
            var plugins = navigator.plugins;
            var pluginList = [];
            if (plugins) {
                for (var pi = 0; pi < plugins.length; pi++) {
                    var p = plugins[pi];
                    pluginList.push(p.name + '|' + p.filename);
                }
            }
            info.plugins = pluginList.join(',');
        } catch(e) {
            info.plugins = 'lỗi';
        }

        // WebGL fingerprint (extended)
        try {
            var gl = document.createElement('canvas').getContext('webgl')
                  || document.createElement('canvas').getContext('experimental-webgl');
            if (gl) {
                var debugInfo = gl.getExtension('WEBGL_debug_renderer_info');
                info.webglVendor = debugInfo
                    ? gl.getParameter(debugInfo.UNMASKED_VENDOR_WEBGL)
                    : 'bị ẩn';
                info.webglRenderer = debugInfo
                    ? gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL)
                    : 'bị ẩn';
                info.webglVersion = gl.getParameter(gl.VERSION);
                info.webglShadingVersion = gl.getParameter(gl.SHADING_LANGUAGE_VERSION);
                info.webglMaxTextureSize = gl.getParameter(gl.MAX_TEXTURE_SIZE);
                var vp = gl.getParameter(gl.MAX_VIEWPORT_DIMS);
                info.webglMaxViewport = vp[0] + 'x' + vp[1];
                info.webglMaxRbSize = gl.getParameter(gl.MAX_RENDERBUFFER_SIZE);
                var ext = gl.getSupportedExtensions();
                info.webglExtensions = ext ? ext.length : 0;
            } else {
                info.webglVendor = 'không hỗ trợ';
                info.webglRenderer = 'không hỗ trợ';
            }
        } catch(e) {
            info.webglVendor = 'lỗi';
            info.webglRenderer = 'lỗi';
        }

        // Canvas fingerprint (enhanced)
        try {
            var c = document.createElement('canvas');
            c.width = 280; c.height = 110;
            var ctx = c.getContext('2d');

            // Background with gradient
            var grad = ctx.createLinearGradient(0, 0, 280, 110);
            grad.addColorStop(0, '#f60');
            grad.addColorStop(0.5, '#09f');
            grad.addColorStop(1, '#0f6');
            ctx.fillStyle = grad;
            ctx.fillRect(0, 0, 280, 110);

            // Text with multiple fonts and styles
            ctx.font = 'bold 13px Arial';
            ctx.fillStyle = '#069';
            ctx.fillText('Browser Fingerprint Test 123!', 5, 15);
            ctx.font = 'italic 16px "Times New Roman"';
            ctx.fillStyle = 'rgba(200, 0, 0, 0.7)';
            ctx.fillText('Censorship bypass check', 5, 35);

            // Emoji rendering (high OS/font variance)
            ctx.font = '20px "Segoe UI Emoji", "Apple Color Emoji", "Noto Color Emoji", sans-serif';
            ctx.fillText('🙂🎉🔒💻🌍', 5, 60);

            // Bezier curve
            ctx.beginPath();
            ctx.moveTo(10, 70);
            ctx.bezierCurveTo(80, 45, 20, 95, 140, 75);
            ctx.strokeStyle = '#333';
            ctx.lineWidth = 1.5;
            ctx.stroke();

            // Arc/circle
            ctx.beginPath();
            ctx.arc(200, 80, 15, 0, Math.PI * 2, false);
            ctx.fillStyle = 'rgba(255, 215, 0, 0.6)';
            ctx.fill();
            ctx.strokeStyle = '#800';
            ctx.lineWidth = 1;
            ctx.stroke();

            // Anti-alias sensitive thin angled line
            ctx.beginPath();
            ctx.moveTo(220, 65);
            ctx.lineTo(275, 100);
            ctx.strokeStyle = '#000';
            ctx.lineWidth = 0.5;
            ctx.stroke();

            // Timezone offset as payload
            ctx.font = '9px Consolas, monospace';
            ctx.fillStyle = '#111';
            ctx.fillText((new Date()).getTimezoneOffset().toString(), 5, 105);

            var dataUrl = c.toDataURL();
            var hash = 0;
            for (var i = 0; i < dataUrl.length; i++) {
                hash = ((hash << 5) - hash) + dataUrl.charCodeAt(i);
                hash = hash >>> 0;
            }
            info.canvasHash = hash.toString(16);
        } catch(e) {
            info.canvasHash = 'lỗi';
        }

        info.audioHash = null;  // collected async via OfflineAudioContext

        // Font fingerprint (expanded list)
        try {
            var testFonts = [
                'Arial', 'Times New Roman', 'Courier New', 'Georgia', 'Verdana',
                'Comic Sans MS', 'Trebuchet MS', 'Tahoma', 'Segoe UI',
                'Calibri', 'Cambria', 'Consolas', 'Palatino Linotype',
                'Impact', 'Lucida Console', 'MS Sans Serif', 'MS Serif',
                'Symbol', 'Webdings', 'Wingdings',
                'Arial Black', 'Arial Narrow', 'Bahnschrift',
                'Baskerville Old Face', 'Bell MT', 'Bodoni MT',
                'Book Antiqua', 'Bookman Old Style', 'Bradley Hand ITC',
                'Century Gothic', 'Century Schoolbook', 'Corbel',
                'Constantia', 'Copperplate Gothic', 'Courier',
                'Franklin Gothic Medium', 'Gabriola', 'Gadugi', 'Garamond',
                'Ink Free', 'Javanese Text', 'Leelawadee UI',
                'Lucida Sans', 'Lucida Sans Unicode', 'Malgun Gothic',
                'Marlett', 'Microsoft Himalaya', 'Modern',
                'Mongolian Baiti', 'MS Gothic', 'MV Boli', 'Myanmar Text',
                'Nirmala UI', 'Rockwell', 'Segoe Print', 'Segoe Script',
                'Sitka', 'Sylfaen',
            ];
            var available = [];
            var span = document.createElement('span');
            span.style.cssText = 'font-size:72px;visibility:hidden;position:absolute;left:-9999px';
            span.textContent = 'mmmmmmmmmmlli';
            document.body.appendChild(span);
            try {
                var monoW = null;
                for (var k = 0; k < testFonts.length; k++) {
                    span.style.fontFamily = 'monospace';
                    if (monoW === null) monoW = span.offsetWidth;
                    span.style.fontFamily = '"' + testFonts[k] + '", monospace';
                    if (span.offsetWidth !== monoW) available.push(testFonts[k]);
                }
            } finally {
                document.body.removeChild(span);
            }
            info.fonts = available.length + '/' + testFonts.length + ': ' + available.join(', ');
        } catch(e) {
            info.fonts = 'lỗi';
        }

        return info;
    """)


def _collect_async_fingerprint(driver: WebDriver) -> tuple[str, str]:
    try:
        result_json = driver.execute_async_script(r"""
            var callback = arguments[arguments.length - 1];
            var result = { webrtc: '', audioHash: '' };
            var finished = false;
            var webrtcDone = false;
            var audioDone = false;

            function maybeFinish() {
                if (finished) return;
                if (webrtcDone && audioDone) {
                    finished = true;
                    callback(JSON.stringify(result));
                }
            }

            // --- WebRTC ---
            (function() {
                var ips = [];
                var pc = null;

                function finishWebRTC(value) {
                    if (webrtcDone) return;
                    webrtcDone = true;
                    result.webrtc = value;
                    try { if (pc) pc.close(); } catch(e) {}
                    maybeFinish();
                }

                try {
                    pc = new RTCPeerConnection({
                        iceServers: [{urls: 'stun:stun.l.google.com:19302'}]
                    });
                    pc.createDataChannel('');
                    pc.createOffer().then(function(offer) {
                        return pc.setLocalDescription(offer);
                    }).catch(function() {
                        finishWebRTC('lỗi');
                    });
                    pc.onicecandidate = function(e) {
                        if (!e.candidate) {
                            finishWebRTC(ips.join(','));
                            return;
                        }
                        var candidateStr = e.candidate.candidate;
                        var ipMatch = candidateStr.match(
                            /\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b/
                        ) || candidateStr.match(
                            /\b([0-9a-fA-F:]+:+[0-9a-fA-F:]+)\b/
                        );
                        if (ipMatch) {
                            var ip = ipMatch[1];
                            if (ip && ip.indexOf('.local') === -1 && ips.indexOf(ip) === -1) {
                                ips.push(ip);
                            }
                        }
                    };
                } catch(e) {
                    finishWebRTC('lỗi');
                }
                setTimeout(function() {
                    finishWebRTC(ips.join(','));
                }, 3000);
            })();

            // --- Audio fingerprint using OfflineAudioContext ---
            (function() {
                function finishAudio(value) {
                    if (audioDone) return;
                    audioDone = true;
                    result.audioHash = value;
                    maybeFinish();
                }

                try {
                    var sampleRate = 44100;
                    var ac = new (window.OfflineAudioContext || window.webkitOfflineAudioContext)(
                        1, sampleRate * 2, sampleRate
                    );
                    var osc = ac.createOscillator();
                    var compressor = ac.createDynamicsCompressor();
                    osc.type = 'triangle';
                    osc.frequency.setValueAtTime(10000, 0);
                    osc.connect(compressor);
                    compressor.connect(ac.destination);
                    osc.start(0);
                    osc.stop(1);
                    ac.startRendering().then(function(buffer) {
                        var channel = buffer.getChannelData(0);
                        var hash = 0;
                        for (var i = 0; i < channel.length; i++) {
                            var val = channel[i];
                            hash = ((hash << 5) - hash) + (val * 1000000);
                            hash = hash >>> 0;
                        }
                        finishAudio(Math.abs(hash).toString(16).substring(0, 8));
                    }).catch(function() {
                        finishAudio('lỗi');
                    });
                } catch(e) {
                    finishAudio('lỗi');
                }
                setTimeout(function() {
                    finishAudio('timeout');
                }, 5000);
            })();
        """)
        data = json.loads(result_json)
        webrtc = data.get("webrtc", "")
        audio = data.get("audioHash", "")
        logger.info("WebRTC IP  : %s", webrtc if webrtc else "không rò rỉ / không hỗ trợ")
        audio_display = (
            audio if audio and audio not in ("lỗi", "timeout") else "không thu thập được"
        )
        logger.info("Audio hash : %s", audio_display)
        return webrtc, audio
    except (WebDriverException, json.JSONDecodeError):
        logger.info("WebRTC IP  : không kiểm tra được")
        logger.info("Audio hash : không thu thập được")
        return "", ""


def _collect_browser_network_info(driver: WebDriver) -> tuple[str, dict]:
    try:
        network_info = driver.execute_async_script(r"""
            var callback = arguments[arguments.length - 1];
            var finished = false;
            var timeoutMs = arguments[0] || 5000;

            function done(payload) {
                if (!finished) {
                    finished = true;
                    callback(JSON.stringify(payload));
                }
            }

            function _tryFetchIp(services, index) {
                index = index || 0;
                if (index >= services.length) return Promise.resolve('');
                var url = services[index];
                return fetch(url, {cache: 'no-store'}).then(function(r) {
                    if (!r.ok) return _tryFetchIp(services, index + 1);
                    return r.text().then(function(text) {
                        text = (text || '').trim();
                        if (text.startsWith('{')) {
                            var d = JSON.parse(text);
                            if (d && d.ip) return d.ip;
                        } else if (/^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$/.test(text)) {
                            return text;
                        }
                        return _tryFetchIp(services, index + 1);
                    });
                }).catch(function() {
                    return _tryFetchIp(services, index + 1);
                });
            }

            var ipPromise = _tryFetchIp([
                'https://api.ipify.org?format=json',
                'https://api64.ipify.org?format=json',
                'https://icanhazip.com',
                'https://ifconfig.me/ip',
            ]);

            var headersPromise = fetch('https://httpbin.org/headers', {
                cache: 'no-store',
            })
                .then(function(r) { return r.json(); })
                .then(function(d) { return d.headers || {}; })
                .catch(function() { return {}; });

            Promise.all([ipPromise, headersPromise]).then(function(values) {
                done({externalIp: values[0], headers: values[1]});
            });

            setTimeout(function() {
                done({externalIp: '', headers: {}, timedOut: true});
            }, timeoutMs);
        """, NETWORK_INFO_TIMEOUT_MS)
        data = json.loads(network_info)
    except (WebDriverException, json.JSONDecodeError, TypeError):
        logger.info("IP Chrome   : không xác định được")
        logger.info("Proxy       : không kiểm tra được")
        return "", {}

    external_ip = str(data.get("externalIp", "") or "")
    proxy_headers = data.get("headers", {}) or {}
    if not isinstance(proxy_headers, dict):
        proxy_headers = {}

    logger.info("IP Chrome   : %s", external_ip or "không xác định được")

    # httpbin trả về headers với casing gốc; kiểm tra các biến thể phổ biến
    proxy_keys_lower = {k.lower(): v for k, v in proxy_headers.items()}
    forwarded = str(proxy_keys_lower.get("x-forwarded-for", "") or "")
    real_ip = str(proxy_keys_lower.get("x-real-ip", "") or "")
    via = str(proxy_keys_lower.get("via", "") or "")
    if forwarded or real_ip or via:
        logger.info(
            "Proxy       : CÓ (X-Forwarded-For=%s, X-Real-Ip=%s, Via=%s)",
            forwarded or "-",
            real_ip or "-",
            via or "-",
        )
    else:
        logger.info("Proxy       : không phát hiện header proxy")

    return external_ip, proxy_headers


_TIMEZONE_LANG_MAP = {
    "Asia/Saigon": ("vi",),
    "Asia/Ho_Chi_Minh": ("vi",),
    "Asia/Bangkok": ("th",),
    "Asia/Jakarta": ("id",),
    "Asia/Shanghai": ("zh",),
    "Asia/Tokyo": ("ja",),
    "Asia/Seoul": ("ko",),
    "America/New_York": ("en",),
    "America/Chicago": ("en",),
    "America/Los_Angeles": ("en",),
    "Europe/London": ("en",),
    "Europe/Paris": ("fr",),
    "Europe/Berlin": ("de",),
}


def _is_global_ip_candidate(ip: str) -> bool:
    if not ip or ".local" in ip:
        return False

    try:
        return ipaddress.ip_address(ip).is_global
    except ValueError:
        return False


def _extract_global_webrtc_ips(webrtc_ips: str) -> list[str]:
    global_ips: list[str] = []
    for ip in webrtc_ips.split(","):
        candidate = ip.strip()
        if _is_global_ip_candidate(candidate) and candidate not in global_ips:
            global_ips.append(candidate)
    return global_ips


def _save_fingerprint_json(
    info: dict,
    webrtc_ips: str,
    external_ip: str,
    proxy_headers: dict,
    data_dir: Path,
) -> None:
    fp_dir = data_dir / "fingerprints"
    try:
        fp_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        logger.warning("Không thể tạo thư mục fingerprints: %s", fp_dir)
        return

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    fingerprint_data = {
        "timestamp": timestamp,
        "info": {k: str(v) for k, v in info.items() if k != "audioHash"},
        "audioHash": info.get("audioHash", ""),
        "webrtcIps": webrtc_ips,
        "externalIp": external_ip,
        "proxyHeaders": {str(k): str(v) for k, v in proxy_headers.items()},
    }

    filepath = fp_dir / f"fp_{timestamp}.json"
    try:
        filepath.write_text(
            json.dumps(fingerprint_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        logger.warning("Không thể ghi fingerprint: %s", filepath)
        return

    latest_path = fp_dir / "latest.json"
    try:
        latest_path.write_text(
            json.dumps(fingerprint_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass

    logger.info("Đã lưu fingerprint vào: %s", filepath)


def _load_previous_fingerprint(data_dir: Path) -> dict | None:
    latest_path = data_dir / "fingerprints" / "latest.json"
    if not latest_path.is_file():
        return None
    try:
        return json.loads(latest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        logger.debug("Không đọc được fingerprint trước đó", exc_info=True)
        return None


def _analyze_and_conclude(
    info: dict,
    webrtc_ips: str,
    external_ip: str,
    proxy_headers: dict,
    data_dir: Path | None = None,
) -> None:
    flags: list[tuple[str, str]] = []  # (risk level, message)

    # ---- 1. WebDriver ----
    if info.get("webdriver") is True:
        flags.append((
            "HIGH",
            "WebDriver = TRUE — trình duyệt có dấu hiệu đang chạy qua Selenium",
        ))

    # ---- 1b. Vendor ----
    vendor = str(info.get("vendor", ""))
    if vendor and vendor != "Google Inc.":
        flags.append((
            "MEDIUM",
            f"vendor = '{vendor}' — Chrome mong đợi 'Google Inc.'",
        ))

    # ---- 1c. productSub ----
    product_sub = str(info.get("productSub", ""))
    if product_sub and product_sub != "20030107":
        flags.append((
            "LOW",
            f"productSub = '{product_sub}' — Chrome mong đợi '20030107'",
        ))

    # ---- 2. Audio fingerprint ----
    audio_hash = info.get("audioHash", "")
    if not audio_hash or audio_hash in ("0", "00000000", "lỗi", "timeout"):
        flags.append((
            "MEDIUM",
            f"Audio hash = {audio_hash or 'rỗng'} — không có fingerprint âm thanh",
        ))

    # ---- 3. Canvas fingerprint ----
    canvas_hash = info.get("canvasHash", "")
    if canvas_hash in ("0", "00000000", ""):
        flags.append(("MEDIUM", "Canvas hash = 0 — không có fingerprint canvas"))

    if data_dir and canvas_hash and canvas_hash != "lỗi":
        previous = _load_previous_fingerprint(data_dir)
        if previous:
            prev_info = previous.get("info", {})
            prev_canvas = prev_info.get("canvasHash", "")
            if prev_canvas and prev_canvas != canvas_hash:
                flags.append((
                    "MEDIUM",
                    f"Canvas hash thay đổi so với lần trước ({prev_canvas[:8]}... → {canvas_hash[:8]}...)",
                ))

    # ---- 4. Language vs Timezone ----
    language = str(info.get("language", ""))
    timezone = str(info.get("timezone", ""))
    lang_code = language.split("-")[0].lower() if language else ""

    expected_langs = _TIMEZONE_LANG_MAP.get(timezone, None)
    if expected_langs is not None and lang_code not in expected_langs:
        flags.append((
            "NOTE",
            f"Ngôn ngữ '{language}' không khớp múi giờ '{timezone}' "
            f"(mong đợi: {expected_langs})",
        ))
    elif expected_langs is None and timezone:
        flags.append((
            "NOTE",
            f"Múi giờ '{timezone}' không có trong danh sách đối chiếu — "
            "cần kiểm tra thủ công",
        ))

    # ---- 5. Platform consistency ----
    platform = str(info.get("platform", ""))
    if platform:
        if "Win32" not in platform and "Win64" not in platform and "Windows" not in platform:
            flags.append((
                "NOTE",
                f"platform = '{platform}' — không giống Windows (mong đợi Win32/Win64)",
            ))

    # ---- 5b. Fonts ----
    fonts_str = str(info.get("fonts", ""))
    font_count = 0
    font_total = 55
    if fonts_str and fonts_str != "N/A" and fonts_str != "lỗi":
        try:
            parts = fonts_str.split("/")
            font_count = int(parts[0])
            if len(parts) > 1:
                font_total = int(parts[1].split(":")[0].strip())
        except (ValueError, IndexError):
            pass

    if platform and ("Win32" in platform or "Win64" in platform or "Windows" in platform):
        if font_count > 0 and font_count < 12:
            flags.append((
                "MEDIUM",
                f"Chỉ có {font_count}/{font_total} font — Windows thường có 30+ font",
            ))
        if fonts_str != "lỗi" and "Segoe UI" not in fonts_str and fonts_str != "N/A":
            flags.append(("NOTE", "Thiếu font 'Segoe UI' — font mặc định của Windows"))

    # ---- 6. WebRTC leak vs External IP ----
    webrtc_public_ips = _extract_global_webrtc_ips(webrtc_ips)

    if webrtc_public_ips and external_ip:
        for pub_ip in webrtc_public_ips:
            if pub_ip == external_ip:
                break
        else:
            flags.append((
                "MEDIUM",
                f"WebRTC IP ({', '.join(webrtc_public_ips)}) khác IP Chrome ({external_ip}) "
                "— có thể đang rò rỉ IP ngoài proxy/VPN",
            ))

    if not webrtc_ips or webrtc_ips == "lỗi":
        flags.append(("NOTE", "WebRTC không trả về IP — có thể đã bị tắt hoặc bị chặn"))

    # ---- 7. Proxy headers ----
    forwarded = proxy_headers.get("X-Forwarded-For", "")
    via = proxy_headers.get("Via", "")
    if forwarded or via:
        flags.append((
            "MEDIUM",
            f"Phát hiện header proxy: X-Forwarded-For={forwarded}, Via={via}",
        ))

    # ---- 8. Screen / Window consistency ----
    screen_w = int(info.get("screenW", 0))
    window_w = int(info.get("windowW", 0))
    if screen_w > 0 and window_w > screen_w:
        flags.append((
            "LOW",
            f"Cửa sổ ({window_w}px) lớn hơn màn hình ({screen_w}px) — bất thường",
        ))

    # ---- 8b. Color depth ----
    color_depth = info.get("colorDepth")
    if color_depth is not None and color_depth != 24:
        flags.append((
            "LOW",
            f"colorDepth = {color_depth} — màn hình thường là 24",
        ))

    # ---- 8c. Touch support ----
    touch_support = info.get("touchSupport")
    max_touch = info.get("maxTouchPoints", 0)
    if touch_support or max_touch > 0:
        flags.append((
            "NOTE",
            f"Cảm ứng = {touch_support}, maxTouchPoints = {max_touch} "
            "— desktop thường không có",
        ))

    # ---- Kết luận ----
    logger.info("--- Phân tích fingerprint ---")
    has_high = any(level == "HIGH" for level, _ in flags)
    has_medium = any(level == "MEDIUM" for level, _ in flags)
    has_low = any(level == "LOW" for level, _ in flags)

    if not flags:
        logger.info("Kết quả: không phát hiện bất thường trong các kiểm tra hiện có")
        return

    for level, msg in flags:
        if level == "HIGH":
            logger.warning("[RỦI RO CAO] %s", msg)
        elif level == "MEDIUM":
            logger.warning("[RỦI RO TRUNG BÌNH] %s", msg)
        elif level == "LOW":
            logger.info("[RỦI RO THẤP] %s", msg)
        else:
            logger.info("[GHI CHÚ] %s", msg)

    if has_high:
        logger.error("KẾT LUẬN: RỦI RO CAO — cần kiểm tra lại môi trường trình duyệt")
    elif has_medium:
        logger.warning("KẾT LUẬN: RỦI RO TRUNG BÌNH — có điểm cần kiểm tra lại")
    elif has_low:
        logger.info("KẾT LUẬN: RỦI RO THẤP — chỉ có dấu hiệu phụ")
    else:
        logger.info("KẾT LUẬN: chỉ có ghi chú, chưa thấy rủi ro rõ ràng")
