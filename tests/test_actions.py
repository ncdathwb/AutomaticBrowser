import unittest

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from autobrowser.browser.actions.elements import by_css, by_id, by_name, by_xpath
from autobrowser.browser.actions.keyboard import (
    press_enter,
    send_keys,
    type_text,
    type_text_human,
)


class FakeElement:
    def __init__(self):
        self.cleared = False
        self.sent_keys = []

    def clear(self):
        self.cleared = True

    def send_keys(self, *keys):
        self.sent_keys.append(keys)


class ActionHelperTests(unittest.TestCase):
    def test_locator_builders(self):
        self.assertEqual(by_css(".button"), (By.CSS_SELECTOR, ".button"))
        self.assertEqual(by_id("submit"), (By.ID, "submit"))
        self.assertEqual(by_name("email"), (By.NAME, "email"))
        self.assertEqual(by_xpath("//button"), (By.XPATH, "//button"))

    def test_type_text_clears_and_submits(self):
        element = FakeElement()

        result = type_text(element, "hello", submit=True)

        self.assertIs(result, element)
        self.assertTrue(element.cleared)
        self.assertEqual(element.sent_keys, [("hello",), (Keys.ENTER,)])

    def test_type_text_can_skip_clear(self):
        element = FakeElement()

        type_text(element, "hello", clear=False)

        self.assertFalse(element.cleared)
        self.assertEqual(element.sent_keys, [("hello",)])

    def test_type_text_human_sends_characters_one_by_one(self):
        element = FakeElement()
        sleeps = []

        result = type_text_human(
            element,
            "ab",
            submit=True,
            key_delay_seconds=(0, 0),
            pause_seconds=(0, 0),
            pause_chance=0,
            sleep=sleeps.append,
        )

        self.assertIs(result, element)
        self.assertTrue(element.cleared)
        self.assertEqual(element.sent_keys, [("a",), ("b",), (Keys.ENTER,)])
        self.assertEqual(sleeps, [0, 0, 0])

    def test_press_enter_and_send_keys_return_element(self):
        element = FakeElement()

        self.assertIs(press_enter(element), element)
        self.assertIs(send_keys(element, "a", "b"), element)
        self.assertEqual(element.sent_keys, [(Keys.ENTER,), ("a", "b")])


if __name__ == "__main__":
    unittest.main()
