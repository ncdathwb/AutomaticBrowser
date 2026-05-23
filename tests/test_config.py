import unittest
from pathlib import Path

from autobrowser.config import (
    APP_NAME,
    DEFAULT_LOG_LEVEL,
    build_app_config,
    build_browser_config,
    load_dotenv_file,
)


class ConfigTests(unittest.TestCase):
    def test_default_data_paths_use_local_app_data(self):
        env = {"LOCALAPPDATA": r"C:\Users\HP\AppData\Local"}

        app_config = build_app_config(env)
        browser_config = build_browser_config(app_config, env)

        expected_data_dir = Path(env["LOCALAPPDATA"]) / APP_NAME
        self.assertEqual(app_config.data_dir, expected_data_dir)
        self.assertEqual(app_config.runtime_dir, expected_data_dir / "runtime")
        self.assertEqual(app_config.log_file, expected_data_dir / "logs" / "autobrowser.log")
        self.assertEqual(browser_config.profile_dir, expected_data_dir / "chrome_profile")
        self.assertEqual(
            browser_config.driver_path_cache_file,
            expected_data_dir / "runtime" / "chromedriver_path.txt",
        )

    def test_data_dir_env_override_wins_over_local_app_data(self):
        env = {
            "AUTOBROWSER_DATA_DIR": r"D:\AutoBrowserData",
            "LOCALAPPDATA": r"C:\Users\HP\AppData\Local",
        }

        app_config = build_app_config(env)
        browser_config = build_browser_config(app_config, env)

        expected_data_dir = Path(env["AUTOBROWSER_DATA_DIR"])
        self.assertEqual(app_config.data_dir, expected_data_dir)
        self.assertEqual(browser_config.profile_dir, expected_data_dir / "chrome_profile")

    def test_invalid_log_level_falls_back_to_info(self):
        env = {
            "LOCALAPPDATA": r"C:\Users\HP\AppData\Local",
            "AUTOBROWSER_LOG_LEVEL": "very-noisy",
        }

        app_config = build_app_config(env)

        self.assertEqual(app_config.log_level, DEFAULT_LOG_LEVEL)

    def test_load_dotenv_file_adds_missing_values(self):
        env = {}
        dotenv_path = Path("tests/.tmp.env")
        dotenv_path.write_text(
            "AUTOBROWSER_LOGIN_ACCOUNT=test_user\nAUTOBROWSER_LOGIN_PASSWORD='secret value'\n",
            encoding="utf-8",
        )

        try:
            load_dotenv_file(dotenv_path, env)
        finally:
            dotenv_path.unlink(missing_ok=True)

        self.assertEqual(env["AUTOBROWSER_LOGIN_ACCOUNT"], "test_user")
        self.assertEqual(env["AUTOBROWSER_LOGIN_PASSWORD"], "secret value")

    def test_load_dotenv_file_does_not_override_existing_env(self):
        env = {"AUTOBROWSER_LOGIN_ACCOUNT": "existing_user"}
        dotenv_path = Path("tests/.tmp.env")
        dotenv_path.write_text(
            "AUTOBROWSER_LOGIN_ACCOUNT=env_user\n",
            encoding="utf-8",
        )

        try:
            load_dotenv_file(dotenv_path, env)
        finally:
            dotenv_path.unlink(missing_ok=True)

        self.assertEqual(env["AUTOBROWSER_LOGIN_ACCOUNT"], "existing_user")


if __name__ == "__main__":
    unittest.main()
