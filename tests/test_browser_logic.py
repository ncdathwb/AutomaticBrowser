import ast
import inspect
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from selenium.webdriver.remote.webdriver import WebDriver

from autobrowser.browser.automation import (
    GOOGLE_URL,
    TARGET_URL,
    ExternalLoginRequired,
    open_target_site,
    run_browser_logic,
    type_login_credentials,
)


class FakeWebDriver(WebDriver):
    def __init__(self, script_result=False):
        self._current_url = TARGET_URL
        self.get_mock = MagicMock()
        self.last_script = None
        self.script_result = script_result

    @property
    def current_url(self):
        return self._current_url

    def get(self, url):
        self.get_mock(url)

    def execute_script(self, script):
        self.last_script = script
        return self.script_result


class BrowserLogicTests(unittest.TestCase):
    def test_run_browser_logic_keeps_stable_single_argument_contract(self):
        signature = inspect.signature(run_browser_logic)

        self.assertEqual(list(signature.parameters), ["session"])
        self.assertIs(signature.return_annotation, str)

    def test_controller_imports_only_automation_entrypoint(self):
        controller_path = Path("autobrowser/controllers/browser_controller.py")
        controller_tree = ast.parse(controller_path.read_text(encoding="utf-8"))

        automation_imports = [
            alias.name
            for node in ast.walk(controller_tree)
            if isinstance(node, ast.ImportFrom)
            if node.module == "autobrowser.browser.automation"
            for alias in node.names
        ]

        self.assertEqual(
            automation_imports,
            ["TARGET_URL", "ExternalLoginRequired", "run_browser_logic"],
        )

    def test_run_browser_logic_opens_target_url(self):
        driver = MagicMock()
        driver.current_url = TARGET_URL
        driver.execute_script.return_value = False
        session = SimpleNamespace(driver=driver, lock=threading.RLock())

        with patch("autobrowser.browser.automation.select_live_browser_window") as select_window:
            current_url = run_browser_logic(session)

        driver.get.assert_any_call(GOOGLE_URL)
        driver.get.assert_any_call(TARGET_URL)
        self.assertEqual(driver.get.call_count, 2)
        self.assertEqual(select_window.call_count, 2)
        self.assertEqual(current_url, TARGET_URL)

    def test_missing_credentials_do_not_submit_login(self):
        driver = FakeWebDriver()

        with self.assertLogs("autobrowser.browser.automation", "WARNING") as logs:
            credentials_entered = type_login_credentials(driver, "", "secret")

        self.assertFalse(credentials_entered)
        self.assertIn("AUTOBROWSER_LOGIN_ACCOUNT", logs.output[0])

    def test_credentials_are_typed_before_submit(self):
        driver = FakeWebDriver()
        account_input = object()
        password_input = object()

        with (
            patch(
                "autobrowser.browser.automation.click",
                side_effect=[account_input, password_input],
            ) as click,
            patch("autobrowser.browser.automation.type_text_human") as type_text_human,
        ):
            credentials_entered = type_login_credentials(driver, "account", "secret")

        self.assertTrue(credentials_entered)
        self.assertEqual(click.call_count, 2)
        type_text_human.assert_any_call(
            account_input,
            "account",
            key_delay_seconds=(0.07, 0.2),
            pause_seconds=(0.25, 0.8),
            pause_chance=0.14,
        )
        type_text_human.assert_any_call(
            password_input,
            "secret",
            key_delay_seconds=(0.07, 0.2),
            pause_seconds=(0.25, 0.8),
            pause_chance=0.14,
        )

    def test_webdriver_detection_requests_external_login_after_submit(self):
        driver = FakeWebDriver(script_result=True)
        session = SimpleNamespace(driver=driver, lock=threading.RLock())

        with (
            patch("autobrowser.browser.automation.select_live_browser_window"),
            patch("autobrowser.browser.automation.wait_for_dom_complete"),
            patch("autobrowser.browser.automation.click_login_button"),
            patch("autobrowser.browser.automation.wait_for_login_form"),
            patch("autobrowser.browser.automation.type_login_credentials", return_value=True),
            patch("autobrowser.browser.automation.submit_login_form") as submit_login_form,
            patch("autobrowser.browser.automation.wait_for_qr_scan"),
        ):
            with (
                self.assertLogs("autobrowser.browser.automation", "WARNING") as logs,
                self.assertRaises(ExternalLoginRequired),
            ):
                open_target_site(session)

        self.assertTrue(any("Selenium" in entry for entry in logs.output))
        driver.get_mock.assert_any_call(GOOGLE_URL)
        driver.get_mock.assert_any_call(TARGET_URL)
        self.assertEqual(driver.get_mock.call_count, 2)
        submit_login_form.assert_called_once_with(driver)


if __name__ == "__main__":
    unittest.main()
