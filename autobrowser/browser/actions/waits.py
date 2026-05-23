from collections.abc import Callable
from typing import Any

from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

Locator = tuple[str, str]

DEFAULT_TIMEOUT_SECONDS = 12.0


def wait_until(
    driver: WebDriver,
    condition: Callable[[WebDriver], Any],
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> Any:
    return WebDriverWait(driver, timeout).until(condition)


def wait_present(
    driver: WebDriver,
    locator: Locator,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> WebElement:
    return wait_until(driver, EC.presence_of_element_located(locator), timeout)


def wait_visible(
    driver: WebDriver,
    locator: Locator,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> WebElement:
    return wait_until(driver, EC.visibility_of_element_located(locator), timeout)


def wait_clickable(
    driver: WebDriver,
    locator: Locator,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> WebElement:
    return wait_until(driver, EC.element_to_be_clickable(locator), timeout)
