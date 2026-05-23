from selenium.webdriver import ActionChains
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement


def click_element(driver: WebDriver, element: WebElement) -> WebElement:
    ActionChains(driver).click(element).perform()
    return element


def double_click_element(driver: WebDriver, element: WebElement) -> WebElement:
    ActionChains(driver).double_click(element).perform()
    return element


def context_click_element(driver: WebDriver, element: WebElement) -> WebElement:
    ActionChains(driver).context_click(element).perform()
    return element


def hover_element(driver: WebDriver, element: WebElement) -> WebElement:
    ActionChains(driver).move_to_element(element).perform()
    return element


def scroll_to_element(driver: WebDriver, element: WebElement) -> WebElement:
    ActionChains(driver).scroll_to_element(element).perform()
    return element
