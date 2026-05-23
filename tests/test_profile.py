import unittest
from pathlib import Path

from autobrowser.browser.profile import normalize_path, normalize_text


class ProfileTests(unittest.TestCase):
    def test_normalize_text_lowercases_and_uses_windows_separators(self):
        self.assertEqual(normalize_text("C:/Users/HP/Profile"), "c:\\users\\hp\\profile")

    def test_normalize_path_uses_normalize_text(self):
        self.assertEqual(
            normalize_path(Path("C:/Users/HP/Profile")),
            "c:\\users\\hp\\profile",
        )


if __name__ == "__main__":
    unittest.main()
