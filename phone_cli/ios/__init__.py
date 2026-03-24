"""iOS facade that routes calls to the active runtime backend."""

from __future__ import annotations

from typing import Any

from phone_cli.ios.connection import (
    DeviceInfo,
    WDAConnection,
    get_wda_client,
    quick_connect,
)
from phone_cli.ios.runtime.base import (
    IOSCapabilities,
    IOSTargetInfo,
    UnsupportedOperationError,
)
from phone_cli.ios.runtime.router import get_backend, normalize_runtime, resolve_runtime


def list_devices(
    runtime: str | None = None,
    state: dict[str, Any] | None = None,
) -> list[IOSTargetInfo]:
    return get_backend(runtime=runtime, state=state).list_targets()


def get_capabilities(
    runtime: str | None = None,
    state: dict[str, Any] | None = None,
) -> dict[str, bool]:
    return get_backend(runtime=runtime, state=state).get_capabilities()


def get_screen_size(
    device_id: str | None = None,
    runtime: str | None = None,
    state: dict[str, Any] | None = None,
) -> tuple[int, int]:
    return get_backend(runtime=runtime, state=state).get_screen_size(target_id=device_id)


def launch_app(
    app_name: str | None = None,
    device_id: str | None = None,
    runtime: str | None = None,
    state: dict[str, Any] | None = None,
    bundle_id: str | None = None,
    app_path: str | None = None,
) -> bool:
    return get_backend(runtime=runtime, state=state).launch_app(
        app_name=app_name,
        bundle_id=bundle_id,
        app_path=app_path,
        target_id=device_id,
    )


def get_current_app(
    device_id: str | None = None,
    runtime: str | None = None,
    state: dict[str, Any] | None = None,
) -> str:
    return get_backend(runtime=runtime, state=state).get_current_app(target_id=device_id)


def get_screenshot(
    device_id: str | None = None,
    runtime: str | None = None,
    state: dict[str, Any] | None = None,
):
    return get_backend(runtime=runtime, state=state).get_screenshot(target_id=device_id)


def tap(
    x: int,
    y: int,
    device_id: str | None = None,
    runtime: str | None = None,
    state: dict[str, Any] | None = None,
) -> None:
    get_backend(runtime=runtime, state=state).tap(x, y, target_id=device_id)


def double_tap(
    x: int,
    y: int,
    device_id: str | None = None,
    runtime: str | None = None,
    state: dict[str, Any] | None = None,
) -> None:
    get_backend(runtime=runtime, state=state).double_tap(x, y, target_id=device_id)


def long_press(
    x: int,
    y: int,
    duration_ms: int = 3000,
    device_id: str | None = None,
    runtime: str | None = None,
    state: dict[str, Any] | None = None,
) -> None:
    get_backend(runtime=runtime, state=state).long_press(
        x,
        y,
        duration_ms=duration_ms,
        target_id=device_id,
    )


def swipe(
    start_x: int,
    start_y: int,
    end_x: int,
    end_y: int,
    duration_ms: int | None = None,
    device_id: str | None = None,
    runtime: str | None = None,
    state: dict[str, Any] | None = None,
) -> None:
    get_backend(runtime=runtime, state=state).swipe(
        start_x,
        start_y,
        end_x,
        end_y,
        duration_ms=duration_ms,
        target_id=device_id,
    )


def type_text(
    text: str,
    device_id: str | None = None,
    runtime: str | None = None,
    state: dict[str, Any] | None = None,
) -> None:
    get_backend(runtime=runtime, state=state).type_text(text, target_id=device_id)


def clear_text(
    device_id: str | None = None,
    runtime: str | None = None,
    state: dict[str, Any] | None = None,
) -> None:
    get_backend(runtime=runtime, state=state).clear_text(target_id=device_id)


def back(
    device_id: str | None = None,
    runtime: str | None = None,
    state: dict[str, Any] | None = None,
) -> None:
    get_backend(runtime=runtime, state=state).back(target_id=device_id)


def home(
    device_id: str | None = None,
    runtime: str | None = None,
    state: dict[str, Any] | None = None,
) -> None:
    get_backend(runtime=runtime, state=state).home(target_id=device_id)


def ui_tree(
    device_id: str | None = None,
    runtime: str | None = None,
    state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return get_backend(runtime=runtime, state=state).ui_tree(target_id=device_id)


def app_state(
    bundle_id: str | None = None,
    device_id: str | None = None,
    runtime: str | None = None,
    state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return get_backend(runtime=runtime, state=state).app_state(
        bundle_id=bundle_id,
        target_id=device_id,
    )


def wait_for_app(
    bundle_id: str,
    timeout: int = 30,
    wait_state: str = "running",
    device_id: str | None = None,
    runtime: str | None = None,
    state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return get_backend(runtime=runtime, state=state).wait_for_app(
        bundle_id=bundle_id,
        timeout=timeout,
        state=wait_state,
        target_id=device_id,
    )


def check_screen(
    threshold: float = 0.95,
    device_id: str | None = None,
    runtime: str | None = None,
    state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return get_backend(runtime=runtime, state=state).check_screen(
        threshold=threshold,
        target_id=device_id,
    )

__all__ = [
    "DeviceInfo",
    "IOSCapabilities",
    "IOSTargetInfo",
    "UnsupportedOperationError",
    "WDAConnection",
    "back",
    "app_state",
    "check_screen",
    "clear_text",
    "double_tap",
    "get_backend",
    "get_capabilities",
    "get_current_app",
    "get_screen_size",
    "get_screenshot",
    "home",
    "launch_app",
    "long_press",
    "get_wda_client",
    "list_devices",
    "normalize_runtime",
    "quick_connect",
    "resolve_runtime",
    "swipe",
    "tap",
    "type_text",
    "ui_tree",
    "wait_for_app",
]
