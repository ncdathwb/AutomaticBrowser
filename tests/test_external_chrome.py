import unittest
from pathlib import Path
from unittest.mock import patch

from autobrowser.browser.external_chrome import launch_external_chrome
from autobrowser.config import BrowserConfig


class ExternalChromeTests(unittest.TestCase):
    def test_launch_external_chrome_uses_requested_url_and_profile(self):
        chrome_path = Path("chrome.exe")
        login_url = "https://www.bhxc969.net/Home/Index"
        config = BrowserConfig(
            profile_dir=Path("profile-dir"),
            driver_path_cache_file=Path("runtime/chromedriver_path.txt"),
        )

        with (
            patch(
                "autobrowser.browser.external_chrome.find_chrome_executable",
                return_value=chrome_path,
            ),
            patch("autobrowser.browser.external_chrome.prepare_profile") as prepare_profile,
            patch("autobrowser.browser.external_chrome.subprocess.Popen") as popen,
        ):
            process = launch_external_chrome(login_url, config)

        self.assertIs(process, popen.return_value)
        prepare_profile.assert_called_once_with(config.profile_dir)
        popen.assert_called_once()
        self.assertEqual(
            popen.call_args.args[0],
            [
                str(chrome_path),
                f"--user-data-dir={config.profile_dir}",
                "--no-first-run",
                "--new-window",
                login_url,
            ],
        )


if __name__ == "__main__":
    unittest.main()
