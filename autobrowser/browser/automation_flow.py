"""YAML-driven automation flow engine.

Reads a flow definition file and executes steps against a WebDriver session.
Supports: navigate, click, type, wait_element, wait_seconds, submit.
Environment variable substitution via ${VAR_NAME} in string values.
"""

import logging
import os
import re
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from selenium.common.exceptions import WebDriverException
from selenium.webdriver.remote.webdriver import WebDriver

from autobrowser.browser.actions.elements import (
    by_css,
    by_id,
    by_name,
    by_xpath,
    click,
)
from autobrowser.browser.actions.keyboard import type_text, type_text_human
from autobrowser.browser.actions.waits import Locator, wait_present, wait_visible

logger = logging.getLogger(__name__)

_ENV_VAR_RE = re.compile(r"\$\{(\w+)\}")


def _resolve(value: str) -> str:
    """Replace ${ENV_VAR} placeholders with environment variable values."""

    def _replacer(match: re.Match) -> str:
        return os.environ.get(match.group(1), "")

    return _ENV_VAR_RE.sub(_replacer, value)


class StepAction(Enum):
    NAVIGATE = "navigate"
    CLICK = "click"
    TYPE = "type"
    SUBMIT = "submit"
    WAIT_ELEMENT = "wait_element"
    WAIT_SECONDS = "wait_seconds"


_BY_MAP: dict[str, Callable[[str], Locator]] = {
    "css": by_css,
    "id": by_id,
    "name": by_name,
    "xpath": by_xpath,
}


@dataclass
class FlowStep:
    action: StepAction
    url: str = ""
    by: str = "css"
    selector: str = ""
    value: str = ""
    human: bool = True
    clear: bool = True
    submit: bool = False
    timeout: float = 15.0
    seconds: float = 1.0
    # Raw input from YAML for error reporting
    _raw: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass
class FlowDefinition:
    name: str
    steps: list[FlowStep]


class FlowError(RuntimeError):
    """Raised when a flow step fails."""

    def __init__(self, step_index: int, step: FlowStep, message: str):
        self.step_index = step_index
        self.step = step
        super().__init__(f"Step {step_index + 1} [{step.action.value}]: {message}")


def _build_locator(step: FlowStep) -> Locator:
    builder = _BY_MAP.get(step.by)
    if not builder:
        raise ValueError(f"Unknown 'by' method: {step.by}. Use: {', '.join(_BY_MAP)}")
    return builder(step.selector)


def parse_flow(yaml_text: str) -> FlowDefinition:
    """Parse a YAML flow definition string into a FlowDefinition."""
    try:
        import yaml
    except ImportError:
        raise ImportError(
            "PyYAML is required for flow definitions. Install with: pip install pyyaml"
        ) from None

    raw = yaml.safe_load(yaml_text)
    if not isinstance(raw, dict):
        raise ValueError("Flow YAML must be a mapping (top-level keys: name, steps)")

    name = str(raw.get("name", "Unnamed Flow"))
    raw_steps: Sequence[dict[str, Any]] = raw.get("steps", [])
    if not raw_steps:
        raise ValueError("Flow must contain at least one step")

    steps: list[FlowStep] = []
    for item in raw_steps:
        action_str = str(item.get("action", "")).lower().strip()
        try:
            action = StepAction(action_str)
        except ValueError:
            raise ValueError(
                f"Unknown action '{action_str}'. Valid: {[a.value for a in StepAction]}"
            ) from None

        step = FlowStep(
            action=action,
            url=_resolve(str(item.get("url", ""))),
            by=str(item.get("by", "css")).lower(),
            selector=str(item.get("selector", "")),
            value=_resolve(str(item.get("value", ""))),
            human=bool(item.get("human", True)),
            clear=bool(item.get("clear", True)),
            submit=bool(item.get("submit", False)),
            timeout=float(item.get("timeout", 15.0)),
            seconds=float(item.get("seconds", 1.0)),
            _raw=item,
        )
        steps.append(step)

    return FlowDefinition(name=name, steps=steps)


def load_flow(path: Path) -> FlowDefinition:
    """Load a flow definition from a YAML file."""
    if not path.is_file():
        raise FileNotFoundError(f"Flow file not found: {path}")
    return parse_flow(path.read_text(encoding="utf-8"))


def execute_flow(
    driver: WebDriver,
    flow: FlowDefinition,
    *,
    on_step_start: Callable[[int, FlowStep], None] | None = None,
    on_step_end: Callable[[int, FlowStep], None] | None = None,
) -> None:
    """Execute all steps in a flow against the given WebDriver.

    Raises FlowError on the first failing step.
    """
    logger.info("Bắt đầu thực thi flow: %s (%d bước)", flow.name, len(flow.steps))

    for i, step in enumerate(flow.steps):
        if on_step_start:
            on_step_start(i, step)
        logger.info("Flow step %d/%d: %s", i + 1, len(flow.steps), step.action.value)

        try:
            _execute_step(driver, step)
        except (WebDriverException, ValueError, KeyError) as e:
            raise FlowError(i, step, str(e)) from e

        if on_step_end:
            on_step_end(i, step)

    logger.info("Flow '%s' hoàn thành (%d bước)", flow.name, len(flow.steps))


def _execute_step(driver: WebDriver, step: FlowStep) -> None:
    if step.action == StepAction.NAVIGATE:
        _step_navigate(driver, step)
    elif step.action == StepAction.CLICK:
        _step_click(driver, step)
    elif step.action == StepAction.TYPE:
        _step_type(driver, step)
    elif step.action == StepAction.SUBMIT:
        _step_submit(driver, step)
    elif step.action == StepAction.WAIT_ELEMENT:
        _step_wait_element(driver, step)
    elif step.action == StepAction.WAIT_SECONDS:
        _step_wait_seconds(step)


def _step_navigate(driver: WebDriver, step: FlowStep) -> None:
    if not step.url:
        raise ValueError("'url' is required for navigate action")
    logger.info("Điều hướng đến: %s", step.url)
    driver.get(step.url)


def _step_click(driver: WebDriver, step: FlowStep) -> None:
    locator = _build_locator(step)
    logger.info("Click: %s='%s'", step.by, step.selector)
    click(driver, locator, step.timeout)


def _step_type(driver: WebDriver, step: FlowStep) -> None:
    locator = _build_locator(step)
    element = wait_present(driver, locator, step.timeout)
    logger.info("Nhập text vào: %s='%s'", step.by, step.selector)
    if step.human:
        type_text_human(element, step.value, clear=step.clear, submit=step.submit)
    else:
        type_text(element, step.value, clear=step.clear, submit=step.submit)


def _step_submit(driver: WebDriver, step: FlowStep) -> None:
    locator = _build_locator(step)
    element = wait_present(driver, locator, step.timeout)
    logger.info("Submit: %s='%s'", step.by, step.selector)
    element.submit()


def _step_wait_element(driver: WebDriver, step: FlowStep) -> None:
    locator = _build_locator(step)
    logger.info("Chờ element: %s='%s' (timeout=%.0fs)", step.by, step.selector, step.timeout)
    wait_visible(driver, locator, step.timeout)


def _step_wait_seconds(step: FlowStep) -> None:
    logger.info("Đợi %.1f giây...", step.seconds)
    time.sleep(step.seconds)


def run_flow_file(driver: WebDriver, path: Path) -> None:
    """High-level helper: load and execute a flow file in one call."""
    flow = load_flow(path)
    execute_flow(driver, flow)
