"""iOS Simulator backend powered by simctl and host event injection."""

from __future__ import annotations

import base64
import json
import os
import plistlib
import re
import subprocess
import time
from io import BytesIO
from typing import Any

from PIL import Image

from phone_cli.config.apps_ios import get_package_name
from phone_cli.ios.host import (
    check_simulator_host_support,
    click_point,
    double_click_point,
    drag_between,
    find_simulator_window,
    long_press_point,
    map_device_point,
    type_text as host_type_text,
)
from phone_cli.ios.runtime.base import BaseIOSBackend, IOSCapabilities, IOSTargetInfo
from phone_cli.ios.runtime.discovery import detect_simulator_candidates
from phone_cli.ios.screenshot import Screenshot


class SimulatorBackend(BaseIOSBackend):
    """Backend for booted iOS Simulator targets."""

    capabilities = IOSCapabilities(
        launch=True,
        app_state=True,
        wait_for_app=True,
        screenshot=True,
        tap=True,
        double_tap=True,
        long_press=True,
        swipe=True,
        type=True,
        check_screen=True,
    )

    def __init__(self) -> None:
        super().__init__(runtime="simulator")
        self._launched_pids: dict[str, dict[str, int]] = {}
        self._foreground_bundle_by_target: dict[str, str] = {}

    def list_targets(self) -> list[IOSTargetInfo]:
        candidates, _ = detect_simulator_candidates()
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
        screenshot = self.get_screenshot(target_id=target_id)
        return screenshot.width, screenshot.height

    def launch_app(
        self,
        app_name: str | None = None,
        bundle_id: str | None = None,
        app_path: str | None = None,
        target_id: str | None = None,
    ) -> bool:
        target_id = self._require_target_id(target_id)
        resolved_bundle_id = bundle_id
        if app_path:
            self._run_simctl(["install", target_id, app_path], timeout=60)
            resolved_bundle_id = resolved_bundle_id or _read_bundle_id_from_app(app_path)
        if not resolved_bundle_id and app_name:
            resolved_bundle_id = get_package_name(app_name)
        if not resolved_bundle_id:
            return False

        result = self._run_simctl(
            ["launch", "--terminate-running-process", target_id, resolved_bundle_id],
            timeout=30,
        )
        pid = _parse_launch_pid(result.stdout)
        if pid is not None:
            self._launched_pids.setdefault(target_id, {})[resolved_bundle_id] = pid
        self._foreground_bundle_by_target[target_id] = resolved_bundle_id
        return True

    def get_screenshot(self, target_id: str | None = None) -> Screenshot:
        target_id = self._require_target_id(target_id)
        png_bytes = self._capture_png_bytes(target_id)
        image = Image.open(BytesIO(png_bytes))
        width, height = image.size
        return Screenshot(
            base64_data=base64.b64encode(png_bytes).decode("utf-8"),
            width=width,
            height=height,
            is_sensitive=False,
        )

    def tap(self, x: int, y: int, target_id: str | None = None) -> None:
        self._activate_simulator_application()
        host_x, host_y = self._map_device_point(target_id, x, y)
        click_point(host_x, host_y)

    def double_tap(self, x: int, y: int, target_id: str | None = None) -> None:
        self._activate_simulator_application()
        host_x, host_y = self._map_device_point(target_id, x, y)
        double_click_point(host_x, host_y)

    def long_press(
        self,
        x: int,
        y: int,
        duration_ms: int = 3000,
        target_id: str | None = None,
    ) -> None:
        self._activate_simulator_application()
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
        self._activate_simulator_application()
        host_start = self._map_device_point(target_id, start_x, start_y)
        host_end = self._map_device_point(target_id, end_x, end_y)
        drag_between(*host_start, *host_end, duration_ms=duration_ms)

    def type_text(self, text: str, target_id: str | None = None) -> None:
        self._require_simulator_host_support()
        self._require_target_id(target_id)
        self._activate_simulator_application()
        host_type_text(text)

    def app_state(
        self,
        bundle_id: str | None = None,
        target_id: str | None = None,
    ) -> dict[str, Any]:
        target_id = self._require_target_id(target_id)
        running_apps = self._get_running_apps(target_id)
        if bundle_id:
            record = running_apps.get(bundle_id, {})
            running = self._is_running_record(record, target_id, bundle_id)
            foreground = running and self._foreground_bundle_by_target.get(target_id) == bundle_id
            return {
                "bundle_id": bundle_id,
                "current_bundle_id": self._foreground_bundle_by_target.get(target_id),
                "running": running,
                "foreground": foreground,
                "resumed": foreground,
                "pid": record.get("pid"),
            }

        current_bundle_id = self._foreground_bundle_by_target.get(target_id)
        record = running_apps.get(current_bundle_id or "", {})
        running = bool(current_bundle_id) and self._is_running_record(record, target_id, current_bundle_id)
        return {
            "bundle_id": current_bundle_id,
            "current_bundle_id": current_bundle_id,
            "running": running,
            "foreground": running,
            "resumed": running,
            "pid": record.get("pid"),
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
            time.sleep(1)
        raise TimeoutError(f"Timed out waiting for {bundle_id} to reach state: {state}")

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
        if not target_id:
            raise RuntimeError("Simulator target_id is required.")
        return target_id

    def _capture_png_bytes(self, target_id: str) -> bytes:
        result = self._run_simctl(
            ["io", target_id, "screenshot", "-"],
            timeout=30,
            text=False,
        )
        if not result.stdout:
            raise RuntimeError("simctl screenshot returned no image data.")
        return result.stdout

    def _run_simctl(
        self,
        args: list[str],
        *,
        timeout: int = 30,
        text: bool = True,
    ) -> subprocess.CompletedProcess[Any]:
        result = subprocess.run(
            ["xcrun", "simctl"] + args,
            capture_output=True,
            text=text,
            timeout=timeout,
            check=False,
        )
        if result.returncode != 0:
            stderr = result.stderr if text else (result.stderr or b"").decode("utf-8", errors="ignore")
            raise RuntimeError(stderr.strip() or f"simctl command failed: {' '.join(args)}")
        return result

    def _require_simulator_host_support(self) -> None:
        support = check_simulator_host_support()
        if not support.supported:
            detail = "; ".join(reason.message for reason in support.reasons)
            raise RuntimeError(detail or "Simulator host automation is unavailable.")

    def _get_running_apps(self, target_id: str) -> dict[str, dict[str, Any]]:
        try:
            result = self._run_simctl(["listapps", target_id], timeout=20, text=False)
        except Exception:
            return {}
        return _parse_listapps_output(result.stdout)

    def _is_running_record(
        self,
        record: dict[str, Any],
        target_id: str,
        bundle_id: str | None,
    ) -> bool:
        pid = record.get("pid")
        if isinstance(pid, int) and pid > 0 and _pid_exists(pid):
            return True
        if bundle_id:
            remembered_pid = self._launched_pids.get(target_id, {}).get(bundle_id)
            if remembered_pid and _pid_exists(remembered_pid):
                record["pid"] = remembered_pid
                return True
        return False

    def _map_device_point(self, target_id: str | None, x: int, y: int) -> tuple[int, int]:
        self._require_simulator_host_support()
        target_id = self._require_target_id(target_id)
        device_name = _get_simulator_name(target_id)
        window = find_simulator_window(device_name=device_name)
        device_size = self.get_screen_size(target_id=target_id)
        return map_device_point(window, device_size, x, y)

    def _activate_simulator_application(self) -> None:
        """Bring Simulator.app to the foreground before host event injection."""

        try:
            from AppKit import (
                NSApplicationActivateIgnoringOtherApps,
                NSRunningApplication,
            )
        except Exception:
            return

        apps = NSRunningApplication.runningApplicationsWithBundleIdentifier_(
            "com.apple.iphonesimulator"
        )
        if apps:
            apps[0].activateWithOptions_(NSApplicationActivateIgnoringOtherApps)


def _parse_launch_pid(stdout: str | None) -> int | None:
    """Extract the launched process ID from simctl launch output."""

    if not stdout:
        return None
    match = re.search(r":\s*(\d+)\s*$", stdout.strip())
    if not match:
        return None
    return int(match.group(1))


def _read_bundle_id_from_app(app_path: str) -> str | None:
    """Read CFBundleIdentifier from a .app bundle."""

    plist_path = os.path.join(app_path, "Info.plist")
    if not os.path.exists(plist_path):
        return None
    with open(plist_path, "rb") as file:
        payload = plistlib.load(file)
    bundle_id = payload.get("CFBundleIdentifier")
    return str(bundle_id) if bundle_id else None


def _coerce_mapping_payload(raw: bytes) -> dict[str, Any]:
    """Try JSON, plist, then plutil conversion for simctl payloads."""

    for parser in (_parse_json_payload, _parse_plist_payload):
        payload = parser(raw)
        if payload is not None:
            return payload

    conversion = subprocess.run(
        ["plutil", "-convert", "json", "-o", "-", "--", "-"],
        input=raw,
        capture_output=True,
        check=False,
    )
    if conversion.returncode == 0 and conversion.stdout:
        payload = _parse_json_payload(conversion.stdout)
        if payload is not None:
            return payload
    return {}


def _parse_json_payload(raw: bytes) -> dict[str, Any] | None:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _parse_plist_payload(raw: bytes) -> dict[str, Any] | None:
    try:
        payload = plistlib.loads(raw)
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _parse_listapps_output(raw: bytes) -> dict[str, dict[str, Any]]:
    """Normalize simctl listapps output into bundle_id -> record."""

    payload = _coerce_mapping_payload(raw)
    normalized: dict[str, dict[str, Any]] = {}
    for bundle_id, value in payload.items():
        if isinstance(value, dict):
            record = dict(value)
        else:
            record = {"raw": value}

        pid_value = (
            record.get("pid")
            or record.get("PID")
            or record.get("Pid")
            or record.get("ProcessIdentifier")
        )
        if pid_value is not None:
            try:
                record["pid"] = int(pid_value)
            except Exception:
                pass
        normalized[bundle_id] = record
    return normalized


def _pid_exists(pid: int) -> bool:
    """Return whether a process ID is still alive on the host."""

    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _get_simulator_name(target_id: str) -> str | None:
    """Return the human-readable simulator name for a target, if available."""

    for target in detect_simulator_candidates()[0]:
        if target.target_id == target_id:
            return target.label.replace(" (Booted)", "")
    return None
