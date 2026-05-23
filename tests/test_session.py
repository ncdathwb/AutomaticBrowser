import unittest
from pathlib import Path

from autobrowser.browser.session import (
    CHROME_ACCEPT_LANGUAGES,
    CHROME_LANGUAGE,
    build_chrome_options,
)
from autobrowser.config import BrowserConfig


class SessionOptionsTests(unittest.TestCase):
    def test_chrome_language_is_configured_at_browser_level(self):
        config = BrowserConfig(
            profile_dir=Path("profile-dir"),
            driver_path_cache_file=Path("runtime/chromedriver_path.txt"),
        )

        options = build_chrome_options(config)

        self.assertIn(f"--lang={CHROME_LANGUAGE}", options.arguments)
        self.assertEqual(
            options.experimental_options["prefs"]["intl.accept_languages"],
            CHROME_ACCEPT_LANGUAGES,
        )


if __name__ == "__main__":
    unittest.main()
