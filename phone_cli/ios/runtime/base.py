"""Shared types and helpers for iOS runtime backends."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from phone_cli.ios.runtime.discovery import IOSRuntime


@dataclass(frozen=True)
class IOSTargetInfo:
    """Normalized target info that remains compatible with existing CLI usage."""

    target_id: str
    runtime: IOSRuntime
    status: str
    model: str | None = None
    os_version: str | None = None
    name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def device_id(self) -> str:
        """Compatibility alias for existing command handlers."""

        return self.target_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_id": self.target_id,
            "device_id": self.device_id,
            "runtime": self.runtime,
            "status": self.status,
            "model": self.model,
            "os_version": self.os_version,
            "name": self.name,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class IOSCapabilities:
    """Capability matrix reported by a backend."""

    launch: bool = False
    get_current_app: bool = False
    app_state: bool = False
    wait_for_app: bool = False
    screenshot: bool = False
    tap: bool = False
    double_tap: bool = False
    long_press: bool = False
    swipe: bool = False
    type: bool = False
    clear_text: bool = False
    ui_tree: bool = False
    check_screen: bool = False
    install: bool = False
    back: bool = False
    home: bool = False
    app_log: bool = False

    def to_dict(self) -> dict[str, bool]:
        return {
            "launch": self.launch,
            "get_current_app": self.get_current_app,
            "app_state": self.app_state,
            "wait_for_app": self.wait_for_app,
            "screenshot": self.screenshot,
            "tap": self.tap,
            "double_tap": self.double_tap,
            "long_press": self.long_press,
            "swipe": self.swipe,
            "type": self.type,
            "clear_text": self.clear_text,
            "ui_tree": self.ui_tree,
            "check_screen": self.check_screen,
            "install": self.install,
            "back": self.back,
            "home": self.home,
            "app_log": self.app_log,
        }


class UnsupportedOperationError(RuntimeError):
    """Raised when a runtime does not implement a requested operation."""

    def __init__(self, runtime: IOSRuntime, operation: str):
        self.runtime = runtime
        self.operation = operation
        super().__init__(f"{operation} is not supported for iOS runtime: {runtime}")


class IOSBackend(Protocol):
    """Protocol implemented by each iOS runtime backend."""

    runtime: IOSRuntime

    def list_targets(self) -> list[IOSTargetInfo]: ...

    def get_capabilities(self) -> dict[str, bool]: ...

    def get_screen_size(self, target_id: str | None = None) -> tuple[int, int]: ...

    def launch_app(
        self,
        app_name: str | None = None,
        bundle_id: str | None = None,
        app_path: str | None = None,
        target_id: str | None = None,
    ) -> bool: ...

    def get_current_app(self, target_id: str | None = None) -> str: ...

    def get_screenshot(self, target_id: str | None = None): ...

    def tap(self, x: int, y: int, target_id: str | None = None) -> None: ...

    def double_tap(self, x: int, y: int, target_id: str | None = None) -> None: ...

    def long_press(
        self,
        x: int,
        y: int,
        duration_ms: int = 3000,
        target_id: str | None = None,
    ) -> None: ...

    def swipe(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        duration_ms: int | None = None,
        target_id: str | None = None,
    ) -> None: ...

    def type_text(self, text: str, target_id: str | None = None) -> None: ...

    def clear_text(self, target_id: str | None = None) -> None: ...

    def back(self, target_id: str | None = None) -> None: ...

    def home(self, target_id: str | None = None) -> None: ...

    def ui_tree(self, target_id: str | None = None) -> dict[str, Any]: ...

    def app_state(
        self,
        bundle_id: str | None = None,
        target_id: str | None = None,
    ) -> dict[str, Any]: ...

    def wait_for_app(
        self,
        bundle_id: str,
        timeout: int = 30,
        state: str = "running",
        target_id: str | None = None,
    ) -> dict[str, Any]: ...

    def check_screen(
        self,
        threshold: float = 0.95,
        target_id: str | None = None,
    ) -> dict[str, Any]: ...


class BaseIOSBackend:
    """Default backend implementation that raises unsupported operations."""

    runtime: IOSRuntime
    capabilities = IOSCapabilities()

    def __init__(self, runtime: IOSRuntime):
        self.runtime = runtime

    def get_capabilities(self) -> dict[str, bool]:
        return self.capabilities.to_dict()

    def _unsupported(self, operation: str) -> UnsupportedOperationError:
        return UnsupportedOperationError(self.runtime, operation)

    def list_targets(self) -> list[IOSTargetInfo]:
        return []

    def get_screen_size(self, target_id: str | None = None) -> tuple[int, int]:
        raise self._unsupported("get_screen_size")

    def launch_app(
        self,
        app_name: str | None = None,
        bundle_id: str | None = None,
        app_path: str | None = None,
        target_id: str | None = None,
    ) -> bool:
        raise self._unsupported("launch_app")

    def get_current_app(self, target_id: str | None = None) -> str:
        raise self._unsupported("get_current_app")

    def get_screenshot(self, target_id: str | None = None):
        raise self._unsupported("get_screenshot")

    def tap(self, x: int, y: int, target_id: str | None = None) -> None:
        raise self._unsupported("tap")

    def double_tap(self, x: int, y: int, target_id: str | None = None) -> None:
        raise self._unsupported("double_tap")

    def long_press(
        self,
        x: int,
        y: int,
        duration_ms: int = 3000,
        target_id: str | None = None,
    ) -> None:
        raise self._unsupported("long_press")

    def swipe(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        duration_ms: int | None = None,
        target_id: str | None = None,
    ) -> None:
        raise self._unsupported("swipe")

    def type_text(self, text: str, target_id: str | None = None) -> None:
        raise self._unsupported("type_text")

    def clear_text(self, target_id: str | None = None) -> None:
        raise self._unsupported("clear_text")

    def back(self, target_id: str | None = None) -> None:
        raise self._unsupported("back")

    def home(self, target_id: str | None = None) -> None:
        raise self._unsupported("home")

    def ui_tree(self, target_id: str | None = None) -> dict[str, Any]:
        raise self._unsupported("ui_tree")

    def app_state(
        self,
        bundle_id: str | None = None,
        target_id: str | None = None,
    ) -> dict[str, Any]:
        raise self._unsupported("app_state")

    def wait_for_app(
        self,
        bundle_id: str,
        timeout: int = 30,
        state: str = "running",
        target_id: str | None = None,
    ) -> dict[str, Any]:
        raise self._unsupported("wait_for_app")

    def check_screen(
        self,
        threshold: float = 0.95,
        target_id: str | None = None,
    ) -> dict[str, Any]:
        raise self._unsupported("check_screen")
