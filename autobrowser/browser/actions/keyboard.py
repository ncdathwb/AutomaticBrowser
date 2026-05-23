import random
import time

from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webelement import WebElement

DelayRange = tuple[float, float]

DEFAULT_HUMAN_KEY_DELAY_SECONDS: DelayRange = (0.055, 0.18)
DEFAULT_HUMAN_PAUSE_SECONDS: DelayRange = (0.25, 0.75)
DEFAULT_HUMAN_PAUSE_CHANCE = 0.12


def type_text(
    element: WebElement,
    text: str,
    *,
    clear: bool = True,
    submit: bool = False,
) -> WebElement:
    if clear:
        element.clear()

    element.send_keys(text)
    if submit:
        element.send_keys(Keys.ENTER)

    return element


def type_text_human(
    element: WebElement,
    text: str,
    *,
    clear: bool = True,
    submit: bool = False,
    key_delay_seconds: DelayRange = DEFAULT_HUMAN_KEY_DELAY_SECONDS,
    pause_seconds: DelayRange = DEFAULT_HUMAN_PAUSE_SECONDS,
    pause_chance: float = DEFAULT_HUMAN_PAUSE_CHANCE,
    rng: random.Random | None = None,
    sleep=time.sleep,
) -> WebElement:
    current_rng = rng or random.Random()

    if clear:
        element.clear()

    for character in text:
        element.send_keys(character)
        sleep(current_rng.uniform(*key_delay_seconds))

        if character not in "\r\n\t " and current_rng.random() < pause_chance:
            sleep(current_rng.uniform(*pause_seconds))

    if submit:
        sleep(current_rng.uniform(*key_delay_seconds))
        element.send_keys(Keys.ENTER)

    return element


def press_enter(element: WebElement) -> WebElement:
    element.send_keys(Keys.ENTER)
    return element


def send_keys(element: WebElement, *keys: str) -> WebElement:
    element.send_keys(*keys)
    return element
