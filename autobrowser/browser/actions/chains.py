from collections.abc import Callable

from selenium.webdriver import ActionChains
from selenium.webdriver.remote.webdriver import WebDriver


def new_chain(driver: WebDriver) -> ActionChains:
    return ActionChains(driver)


def perform_chain(
    driver: WebDriver,
    build: Callable[[ActionChains], ActionChains | None],
) -> None:
    chain = new_chain(driver)
    result = build(chain)
    (result or chain).perform()
