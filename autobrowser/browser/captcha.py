"""CAPTCHA detection and solving (2captcha integration).

Detection: scans the page for known CAPTCHA iframes/elements.
Solving: submits the CAPTCHA to 2captcha API and injects the token.
"""

import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from selenium.common.exceptions import WebDriverException
from selenium.webdriver.remote.webdriver import WebDriver

logger = logging.getLogger(__name__)

TWOCAPTCHA_API_KEY_ENV = "AUTOBROWSER_2CAPTCHA_API_KEY"

# Common CAPTCHA selectors
_RECAPTCHA_IFRAME_SELECTORS = [
    "iframe[src*='recaptcha']",
    "iframe[src*='google.com/recaptcha']",
]
_HCAPTCHA_IFRAME_SELECTORS = [
    "iframe[src*='hcaptcha']",
    "iframe[src*='hcaptcha.com']",
]
_CAPTCHA_INDICATOR_SELECTORS = [
    ".g-recaptcha",
    ".h-captcha",
    "[data-sitekey]",
    "#captcha",
    ".captcha",
]


def detect_captcha_type(driver: WebDriver) -> str:
    """Detect what type of CAPTCHA is present on the current page.

    Returns one of: 'recaptcha', 'hcaptcha', 'generic', or '' (none found).
    """
    try:
        for selector in _RECAPTCHA_IFRAME_SELECTORS:
            if driver.find_elements("css selector", selector):
                return "recaptcha"
        for selector in _HCAPTCHA_IFRAME_SELECTORS:
            if driver.find_elements("css selector", selector):
                return "hcaptcha"
        for selector in _CAPTCHA_INDICATOR_SELECTORS:
            el = driver.find_elements("css selector", selector)
            if el and any(e.is_displayed() for e in el):
                sitekey = el[0].get_attribute("data-sitekey") if el else ""
                if sitekey:
                    return "recaptcha"
                return "generic"
    except WebDriverException:
        logger.debug("Không kiểm tra được CAPTCHA", exc_info=True)
    return ""


def get_sitekey(driver: WebDriver) -> str:
    """Extract the reCAPTCHA/hCaptcha sitekey from the page."""
    try:
        for selector in [".g-recaptcha", ".h-captcha", "[data-sitekey]"]:
            elements = driver.find_elements("css selector", selector)
            for el in elements:
                sitekey = el.get_attribute("data-sitekey")
                if sitekey:
                    return sitekey
    except WebDriverException:
        pass
    return ""


def solve_captcha(
    driver: WebDriver,
    api_key: str = "",
    timeout: float = 120.0,
) -> str:
    """Solve CAPTCHA via 2captcha and inject the token. Returns the token or ''."""
    api_key = api_key or os.environ.get(TWOCAPTCHA_API_KEY_ENV, "").strip()
    if not api_key:
        logger.warning("Thiếu API key 2captcha. Đặt %s trong .env", TWOCAPTCHA_API_KEY_ENV)
        return ""

    captcha_type = detect_captcha_type(driver)
    if not captcha_type:
        logger.debug("Không phát hiện CAPTCHA trên trang")
        return ""

    sitekey = get_sitekey(driver)
    if not sitekey and captcha_type in ("recaptcha", "hcaptcha"):
        logger.warning("Phát hiện %s nhưng không tìm thấy sitekey", captcha_type)
        return ""

    current_url = ""
    try:
        current_url = driver.current_url or ""
    except WebDriverException:
        pass

    logger.info("Đang giải CAPTCHA (%s) qua 2captcha...", captcha_type)
    token = _submit_2captcha(api_key, current_url, sitekey, captcha_type, timeout)
    if not token:
        return ""

    logger.info("Đã nhận token CAPTCHA, đang inject...")
    _inject_token(driver, token)
    return token


def _submit_2captcha(
    api_key: str,
    page_url: str,
    sitekey: str,
    captcha_type: str,
    timeout: float,
) -> str:
    """Submit CAPTCHA to 2captcha and poll for the token."""
    # Step 1: Submit
    submit_data = {
        "key": api_key,
        "method": "userrecaptcha" if captcha_type == "recaptcha" else "hcaptcha",
        "googlekey": sitekey,
        "pageurl": page_url,
        "json": "1",
    }
    try:
        req = urllib.request.Request(
            "https://api.2captcha.com/in.php",
            data=urllib.parse.urlencode(submit_data).encode("utf-8"),
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
        logger.error("Không gửi được CAPTCHA đến 2captcha: %s", e)
        return ""

    if result.get("status") != 1:
        logger.error("2captcha từ chối: %s", result.get("error_text", result.get("request", "")))
        return ""

    captcha_id = result["request"]

    # Step 2: Poll
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(5)
        try:
            poll_url = (
                f"https://api.2captcha.com/res.php?"
                f"key={api_key}&action=get&id={captcha_id}&json=1"
            )
            with urllib.request.urlopen(poll_url, timeout=10) as resp:
                poll = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, json.JSONDecodeError):
            continue

        if poll.get("status") == 1:
            return str(poll.get("request", ""))
        if poll.get("request") == "ERROR_CAPTCHA_UNSOLVABLE":
            logger.warning("2captcha báo CAPTCHA không giải được")
            return ""

    logger.warning("Hết thời gian chờ 2captcha (%.0fs)", timeout)
    return ""


def _inject_token(driver: WebDriver, token: str) -> None:
    """Inject the solved CAPTCHA token into the page."""
    driver.execute_script(f"""
        var textareas = document.querySelectorAll('textarea[name="g-recaptcha-response"], '
            + 'textarea[name="h-captcha-response"], textarea[name="h-captcha-response"]');
        for (var i = 0; i < textareas.length; i++) {{
            textareas[i].value = '{token}';
        }}
        var callback = window.___grecaptcha_cfg || window.___hcaptcha_cfg;
        if (callback && callback.clients) {{
            for (var clientId in callback.clients) {{
                var client = callback.clients[clientId];
                for (var callbackId in client) {{
                    if (typeof client[callbackId] === 'function') {{
                        client[callbackId]('{token}');
                    }}
                }}
            }}
        }}
    """)


# Convenience: auto-detect + solve wrapper
def handle_captcha_if_present(
    driver: WebDriver,
    api_key: str = "",
    timeout: float = 120.0,
) -> bool:
    """Check for CAPTCHA, solve if found. Returns True if solved or none found."""
    captcha_type = detect_captcha_type(driver)
    if not captcha_type:
        return True  # No CAPTCHA, nothing to do

    logger.info("Phát hiện CAPTCHA loại: %s", captcha_type)
    token = solve_captcha(driver, api_key=api_key, timeout=timeout)
    return bool(token)
