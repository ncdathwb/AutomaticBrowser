import json
import unittest
from unittest.mock import MagicMock, patch

from selenium.common.exceptions import WebDriverException

from autobrowser.browser.automation import (
    QR_MAX_WAIT_SECONDS,
    _collect_browser_network_info,
    _extract_global_webrtc_ips,
    _get_qr_login_state,
    _is_qr_verification_url,
    _reload_page_for_new_qr,
    is_webdriver_detected,
    wait_for_qr_scan,
)


class FakeDriver:
    def __init__(self, script_result):
        self.script_result = script_result

    def execute_script(self, script):
        self.script = script
        return self.script_result


class FakeSwitchTo:
    @property
    def alert(self):
        raise WebDriverException("no alert")


class FakeTextDriver:
    switch_to = FakeSwitchTo()

    def __init__(self, page_text, visible_text=""):
        self.page_text = page_text
        self.visible_text = visible_text

    def execute_script(self, script, *args):
        if "return texts.join" in script:
            return self.page_text
        return self.visible_text


class FakeUrlDriver:
    def __init__(self, urls):
        self.urls = list(urls)

    @property
    def current_url(self):
        if len(self.urls) > 1:
            return self.urls.pop(0)
        return self.urls[0]


class AutomationTests(unittest.TestCase):
    def test_detects_webdriver_true(self):
        driver = FakeDriver(True)

        self.assertTrue(is_webdriver_detected(driver))
        self.assertEqual(driver.script, "return Boolean(window.navigator.webdriver)")

    def test_detects_webdriver_false(self):
        self.assertFalse(is_webdriver_detected(FakeDriver(False)))

    def test_default_qr_wait_refreshes_before_chrome_native_timeout(self):
        self.assertLessEqual(QR_MAX_WAIT_SECONDS, 110)

    def test_qr_state_prioritizes_something_went_wrong_over_passkeys_text(self):
        driver = FakeTextDriver("Passkeys\nSomething went wrong")

        has_passkeys, has_timeout, alert_text = _get_qr_login_state(driver)

        self.assertTrue(has_passkeys)
        self.assertTrue(has_timeout)
        self.assertEqual(alert_text, "")

    def test_detects_qr_verification_url(self):
        driver = FakeUrlDriver(["https://wa.example.net/Home/LoginVerify?param=abc"])

        self.assertTrue(_is_qr_verification_url(driver))

    def test_collect_browser_network_info_uses_browser_script_result(self):
        driver = MagicMock()
        driver.execute_async_script.return_value = json.dumps(
            {
                "externalIp": "203.0.113.10",
                "headers": {"X-Forwarded-For": "198.51.100.20"},
            }
        )

        external_ip, headers = _collect_browser_network_info(driver)

        self.assertEqual(external_ip, "203.0.113.10")
        self.assertEqual(headers["X-Forwarded-For"], "198.51.100.20")
        driver.execute_async_script.assert_called_once()

    def test_extract_global_webrtc_ips_uses_ipaddress_private_ranges(self):
        self.assertEqual(_extract_global_webrtc_ips("172.15.0.1"), ["172.15.0.1"])
        self.assertEqual(_extract_global_webrtc_ips("172.16.0.1"), [])
        self.assertEqual(_extract_global_webrtc_ips("192.168.1.10,host.local"), [])

    def test_detects_when_browser_leaves_qr_verification_url(self):
        driver = MagicMock()

        with (
            patch("autobrowser.browser.automation._wait_for_qr_to_appear", return_value=True),
            patch(
                "autobrowser.browser.automation._get_qr_login_state",
                return_value=(True, False, ""),
            ),
            patch(
                "autobrowser.browser.automation._is_qr_verification_url",
                side_effect=[True, False],
            ),
        ):
            wait_for_qr_scan(
                driver,
                poll_interval=0,
                max_wait=1,
                retry_limit=1,
                sleep=lambda seconds: None,
            )

        driver.execute_script.assert_not_called()

    def test_reload_page_for_new_qr_prefers_visible_browser_navigation(self):
        current_url = "https://wa.example.net/Home/LoginVerify?param=abc"
        driver = MagicMock()
        driver.current_url = current_url

        with patch("autobrowser.browser.automation.wait_for_dom_complete") as wait_dom:
            _reload_page_for_new_qr(driver, sleep=lambda seconds: None)

        driver.get.assert_any_call("about:blank")
        driver.get.assert_any_call(current_url)
        wait_dom.assert_called_once_with(driver)
        driver.execute_script.assert_not_called()

    def test_wait_for_qr_scan_reloads_when_qr_dialog_turns_into_error(self):
        driver = MagicMock()

        with (
            patch(
                "autobrowser.browser.automation._wait_for_qr_to_appear",
                side_effect=[True, False],
            ),
            patch(
                "autobrowser.browser.automation._get_qr_login_state",
                return_value=(True, True, ""),
            ),
            patch("autobrowser.browser.automation._dismiss_alert") as dismiss_alert,
            patch("autobrowser.browser.automation._reload_page_for_new_qr") as reload_page,
        ):
            wait_for_qr_scan(
                driver,
                poll_interval=0,
                max_wait=1,
                retry_limit=2,
                sleep=lambda seconds: None,
            )

        dismiss_alert.assert_called_once_with(driver)
        reload_page.assert_called_once()

    def test_wait_for_qr_scan_keeps_reloading_until_qr_is_scanned(self):
        driver = MagicMock()

        with (
            patch(
                "autobrowser.browser.automation._wait_for_qr_to_appear",
                side_effect=([True] * 12) + [False],
            ),
            patch(
                "autobrowser.browser.automation._get_qr_login_state",
                return_value=(True, True, ""),
            ),
            patch("autobrowser.browser.automation._dismiss_alert"),
            patch("autobrowser.browser.automation._reload_page_for_new_qr") as reload_page,
        ):
            wait_for_qr_scan(
                driver,
                poll_interval=0,
                max_wait=1,
                sleep=lambda seconds: None,
            )

        self.assertEqual(reload_page.call_count, 12)


if __name__ == "__main__":
    unittest.main()
