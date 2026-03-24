"""app_on_mac backend powered by macOS host automation primitives."""

from __future__ import annotations

import base64
import os
import plistlib
import subprocess
import time
from io import BytesIO
from typing import Any

from PIL import Image

from phone_cli.config.apps_ios import get_app_name, get_package_name
from phone_cli.ios.host import (
    capture_window,
    check_app_on_mac_host_support,
    click_point,
    double_click_point,
    drag_between,
    find_app_window,
    flatten_tree,
    get_window,
    list_windows,
    long_press_point,
    map_device_point,
    read_window_tree,
    type_text as host_type_text,
)
from phone_cli.ios.runtime.base import BaseIOSBackend, IOSCapabilities, IOSTargetInfo
from phone_cli.ios.runtime.discovery import detect_app_on_mac_candidates
from phone_cli.ios.screenshot import Screenshot


class AppOnMacBackend(BaseIOSBackend):
    """Backend for iOS apps running directly on an Apple Silicon Mac."""

    capabilities = IOSCapabilities(
        launch=True,
        get_current_app=True,
        app_state=True,
        wait_for_app=True,
        screenshot=True,
        tap=True,
        double_tap=True,
        long_press=True,
        swipe=True,
        type=True,
        ui_tree=True,
        check_screen=True,
    )

    def __init__(self) -> None:
        super().__init__(runtime="app_on_mac")
        self._bound_window_by_target: dict[str, int | str] = {}
        self._bound_bundle_by_target: dict[str, str] = {}

    def list_targets(self) -> list[IOSTargetInfo]:
        candidates, _ = detect_app_on_mac_candidates()
        return [
            IOSTargetInfo(
                target_id=candidate.target_id,
                runtime=candidate.runtime,
                status=candidate.status,
                model=candidate.label,
                name=candidate.label,
                metadata=dict(candidate.metadata),
            )
            for candidate in candidates
        ]

    def get_screen_size(self, target_id: str | None = None) -> tuple[int, int]:
        window = self._resolve_bound_window(target_id=target_id)
        bounds = window.target_bounds()
        return bounds.width, bounds.height

    def launch_app(
        self,
        app_name: str | None = None,
        bundle_id: str | None = None,
        app_path: str | None = None,
        target_id: str | None = None,
    ) -> bool:
        self._require_host_support()
        target_id = self._require_target_id(target_id)

        resolved_bundle_id = bundle_id
        if app_path:
            resolved_bundle_id = resolved_bundle_id or _read_bundle_id_from_app(app_path)
        if not resolved_bundle_id and app_name:
            resolved_bundle_id = get_package_name(app_name)

        if bundle_id:
            self._run_open(["open", "-b", bundle_id])
        elif app_path:
            self._run_open(["open", app_path])
        elif resolved_bundle_id:
            self._run_open(["open", "-b", resolved_bundle_id])
        else:
            return False

        if resolved_bundle_id:
            self._bound_bundle_by_target[target_id] = resolved_bundle_id
            self._bound_window_by_target.pop(target_id, None)
            _activate_application(resolved_bundle_id)
            try:
                window = self._wait_for_window_binding(
                    target_id,
                    bundle_id=resolved_bundle_id,
                )
                self._bound_window_by_target[target_id] = window.window_id
            except Exception:
                pass
        return True

    def get_current_app(self, target_id: str | None = None) -> str:
        target_id = self._require_target_id(target_id)
        bound_bundle_id = self._bound_bundle_by_target.get(target_id)
        if bound_bundle_id and _is_bundle_running(bound_bundle_id):
            try:
                self._resolve_bound_window(target_id=target_id)
                return get_app_name(bound_bundle_id) or bound_bundle_id
            except Exception:
                pass
        bundle_id = _get_foreground_bundle_id()
        if not bundle_id:
            return "Unknown"
        return get_app_name(bundle_id) or bundle_id

    def get_screenshot(self, target_id: str | None = None) -> Screenshot:
        self._require_host_support()
        window = self._resolve_bound_window(target_id=target_id)
        raw = capture_window(window)
        image = Image.open(BytesIO(raw.png_bytes))
        width, height = image.size
        return Screenshot(
            base64_data=base64.b64encode(raw.png_bytes).decode("utf-8"),
            width=width,
            height=height,
            is_sensitive=False,
        )

    def tap(self, x: int, y: int, target_id: str | None = None) -> None:
        self._activate_bound_application(target_id)
        host_x, host_y = self._map_device_point(target_id, x, y)
        click_point(host_x, host_y)

    def double_tap(self, x: int, y: int, target_id: str | None = None) -> None:
        self._activate_bound_application(target_id)
        host_x, host_y = self._map_device_point(target_id, x, y)
        double_click_point(host_x, host_y)

    def long_press(
        self,
        x: int,
        y: int,
        duration_ms: int = 3000,
        target_id: str | None = None,
    ) -> None:
        self._activate_bound_application(target_id)
        host_x, host_y = self._map_device_point(target_id, x, y)
        long_press_point(host_x, host_y, duration_ms=duration_ms)

    def swipe(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        duration_ms: int | None = None,
        target_id: str | None = None,
    ) -> None:
        self._activate_bound_application(target_id)
        host_start = self._map_device_point(target_id, start_x, start_y)
        host_end = self._map_device_point(target_id, end_x, end_y)
        drag_between(*host_start, *host_end, duration_ms=duration_ms)

    def type_text(self, text: str, target_id: str | None = None) -> None:
        self._require_host_support()
        self._activate_bound_application(target_id)
        host_type_text(text)

    def app_state(
        self,
        bundle_id: str | None = None,
        target_id: str | None = None,
    ) -> dict[str, Any]:
        target_id = self._require_target_id(target_id)
        resolved_bundle_id = bundle_id or self._bound_bundle_by_target.get(target_id)
        if resolved_bundle_id:
            running = _is_bundle_running(resolved_bundle_id)
            window_ready = False
            if running:
                try:
                    self._bind_window(target_id, bundle_id=resolved_bundle_id)
                    window_ready = True
                except Exception:
                    pass
            current_bundle_id = _get_foreground_bundle_id()
            foreground = running and (
                current_bundle_id == resolved_bundle_id or window_ready
            )
            return {
                "bundle_id": resolved_bundle_id,
                "current_bundle_id": current_bundle_id,
                "running": running,
                "foreground": foreground,
                "resumed": foreground,
                "window_ready": window_ready,
            }
        current_bundle_id = _get_foreground_bundle_id()
        return {
            "bundle_id": current_bundle_id,
            "current_bundle_id": current_bundle_id,
            "running": bool(current_bundle_id),
            "foreground": bool(current_bundle_id),
            "resumed": bool(current_bundle_id),
            "window_ready": False,
        }

    def wait_for_app(
        self,
        bundle_id: str,
        timeout: int = 30,
        state: str = "running",
        target_id: str | None = None,
    ) -> dict[str, Any]:
        deadline = time.time() + timeout
        state_key = "foreground" if state == "resumed" else state
        while time.time() < deadline:
            current_state = self.app_state(bundle_id=bundle_id, target_id=target_id)
            if current_state.get(state_key):
                return current_state
            if current_state.get("running") and state_key in {"foreground", "resumed"}:
                _activate_application(bundle_id)
                try:
                    self._bind_window(
                        self._require_target_id(target_id),
                        bundle_id=bundle_id,
                    )
                except Exception:
                    pass
            time.sleep(1)
        raise TimeoutError(f"Timed out waiting for {bundle_id} to reach state: {state}")

    def ui_tree(self, target_id: str | None = None) -> dict[str, Any]:
        window = self._resolve_bound_window(target_id=target_id)
        root = read_window_tree(window.window_id)
        return {
            "root": root.to_dict(),
            "elements": flatten_tree(root),
        }

    def check_screen(
        self,
        threshold: float = 0.95,
        target_id: str | None = None,
    ) -> dict[str, Any]:
        shot = self.get_screenshot(target_id=target_id)
        image = Image.open(BytesIO(base64.b64decode(shot.base64_data))).convert("RGB")
        total = max(image.width * image.height, 1)
        black_pixels = 0
        white_pixels = 0
        for y in range(image.height):
            for x in range(image.width):
                r, g, b = image.getpixel((x, y))
                if r <= 16 and g <= 16 and b <= 16:
                    black_pixels += 1
                if r >= 239 and g >= 239 and b >= 239:
                    white_pixels += 1
        black_ratio = black_pixels / total
        white_ratio = white_pixels / total
        if black_ratio >= threshold:
            screen_state = "all_black"
        elif white_ratio >= threshold:
            screen_state = "all_white"
        else:
            screen_state = "normal"
        return {
            "screen_state": screen_state,
            "black_ratio": round(black_ratio, 4),
            "white_ratio": round(white_ratio, 4),
            "threshold": threshold,
        }

    def _require_target_id(self, target_id: str | None) -> str:
        return target_id or "local-mac"

    def _require_host_support(self) -> None:
        support = check_app_on_mac_host_support()
        if not support.supported:
            detail = "; ".join(reason.message for reason in support.reasons)
            raise RuntimeError(detail or "app_on_mac host automation is unavailable.")

    def _run_open(self, command: list[str]) -> None:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            stderr = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(stderr or f"Failed to launch app: {' '.join(command)}")

    def _bind_window(self, target_id: str, bundle_id: str | None = None):
        bound_bundle_id = bundle_id or self._bound_bundle_by_target.get(target_id)
        window = find_app_window(bundle_id=bound_bundle_id)
        if bound_bundle_id:
            self._bound_bundle_by_target[target_id] = bound_bundle_id
        self._bound_window_by_target[target_id] = window.window_id
        return window

    def _resolve_bound_window(self, target_id: str | None = None):
        self._require_host_support()
        target_id = self._require_target_id(target_id)
        bound_bundle_id = self._bound_bundle_by_target.get(target_id)
        window_id = self._bound_window_by_target.get(target_id)
        if window_id is not None:
            try:
                window = get_window(window_id)
                if self._window_matches_target(window, expected_bundle_id=bound_bundle_id):
                    return window
            except Exception:
                pass
            self._bound_window_by_target.pop(target_id, None)

        return self._bind_window(target_id, bundle_id=bound_bundle_id)

    def _map_device_point(self, target_id: str | None, x: int, y: int) -> tuple[int, int]:
        window = self._resolve_bound_window(target_id=target_id)
        device_size = self.get_screen_size(target_id=target_id)
        return map_device_point(window, device_size, x, y)

    def _activate_bound_application(self, target_id: str | None) -> None:
        window = self._resolve_bound_window(target_id=target_id)
        if window.bundle_id:
            _activate_application(window.bundle_id)

    def get_bound_window_id(self, target_id: str | None = None) -> int | str | None:
        """Return the currently bound window ID for the target."""

        target_id = self._require_target_id(target_id)
        return self._bound_window_by_target.get(target_id)

    def get_bound_bundle_id(self, target_id: str | None = None) -> str | None:
        """Return the currently bound bundle ID for the target."""

        target_id = self._require_target_id(target_id)
        return self._bound_bundle_by_target.get(target_id)

    def _wait_for_window_binding(
        self,
        target_id: str,
        bundle_id: str,
        timeout: float = 5.0,
        interval: float = 0.25,
    ):
        deadline = time.time() + timeout
        last_error: Exception | None = None
        while time.time() < deadline:
            try:
                return self._bind_window(target_id, bundle_id=bundle_id)
            except Exception as exc:
                last_error = exc
                _activate_application(bundle_id)
                time.sleep(interval)
        if last_error is not None:
            raise last_error
        raise RuntimeError(f"Timed out waiting to bind window for {bundle_id}")

    def _window_matches_target(
        self,
        window,
        expected_bundle_id: str | None,
    ) -> bool:
        if expected_bundle_id is None:
            return True
        return window.bundle_id == expected_bundle_id


def _read_bundle_id_from_app(app_path: str) -> str | None:
    """Read CFBundleIdentifier from a .app bundle if available."""

    plist_path = os.path.join(app_path, "Info.plist")
    if not os.path.exists(plist_path):
        return None
    with open(plist_path, "rb") as file:
        payload = plistlib.load(file)
    bundle_id = payload.get("CFBundleIdentifier")
    return str(bundle_id) if bundle_id else None


def _get_frontmost_bundle_id() -> str:
    """Return the frontmost application bundle ID."""

    try:
        from AppKit import NSWorkspace
    except Exception:
        return ""

    workspace = NSWorkspace.sharedWorkspace()
    app = workspace.frontmostApplication()
    if app is None:
        return ""
    bundle_id = app.bundleIdentifier()
    return str(bundle_id) if bundle_id else ""


def _get_frontmost_visible_window():
    """Return the top-most visible host window when available."""

    try:
        windows = list_windows()
    except Exception:
        return None
    if not windows:
        return None
    return windows[0]


def _get_frontmost_visible_bundle_id() -> str:
    """Return the bundle ID of the top-most visible host window."""

    window = _get_frontmost_visible_window()
    if window is None or not window.bundle_id:
        return ""
    return str(window.bundle_id)


def _get_foreground_bundle_id() -> str:
    """Prefer visible-window order and fall back to NSWorkspace."""

    return _get_frontmost_visible_bundle_id() or _get_frontmost_bundle_id()


def _is_bundle_running(bundle_id: str) -> bool:
    """Return whether there is at least one running app for a bundle ID."""

    try:
        from AppKit import NSRunningApplication
    except Exception:
        return False
    apps = NSRunningApplication.runningApplicationsWithBundleIdentifier_(bundle_id)
    return bool(apps)


def _activate_application(bundle_id: str) -> None:
    """Bring the target application to the foreground when possible."""

    try:
        from AppKit import (
            NSApplicationActivateIgnoringOtherApps,
            NSRunningApplication,
        )
    except Exception:
        return

    apps = NSRunningApplication.runningApplicationsWithBundleIdentifier_(bundle_id)
    if apps:
        apps[0].activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
