import random
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement

from autobrowser.browser.actions.waits import DEFAULT_TIMEOUT_SECONDS, Locator, wait_clickable

CLICK_PRE_DELAY_RANGE = (0.08, 0.35)
CLICK_POST_DELAY_RANGE = (0.15, 0.55)


def by_css(selector: str) -> Locator:
    return (By.CSS_SELECTOR, selector)


def by_name(name: str) -> Locator:
    return (By.NAME, name)


def by_xpath(xpath: str) -> Locator:
    return (By.XPATH, xpath)


def by_id(element_id: str) -> Locator:
    return (By.ID, element_id)


def click(
    driver: WebDriver,
    locator: Locator,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    rng: random.Random | None = None,
    sleep=time.sleep,
) -> WebElement:
    current_rng = rng or random.Random()
    element = wait_clickable(driver, locator, timeout)
    sleep(current_rng.uniform(*CLICK_PRE_DELAY_RANGE))
    element.click()
    sleep(current_rng.uniform(*CLICK_POST_DELAY_RANGE))
    return element
