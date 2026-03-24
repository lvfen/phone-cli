"""Real-device iOS backend built on top of tidevice + WDA."""

from __future__ import annotations

import base64
import time
import xml.etree.ElementTree as ET
from io import BytesIO
from typing import Any

from PIL import Image

from phone_cli.config.apps_ios import get_package_name
from phone_cli.ios.connection import get_wda_client, list_devices
from phone_cli.ios.device import (
    back as device_back,
    double_tap as device_double_tap,
    get_current_app as device_get_current_app,
    home as device_home,
    long_press as device_long_press,
    swipe as device_swipe,
    tap as device_tap,
)
from phone_cli.ios.input import clear_text as input_clear_text, type_text as input_type_text
from phone_cli.ios.screenshot import Screenshot, get_screenshot
from phone_cli.ios.runtime.base import BaseIOSBackend, IOSCapabilities, IOSTargetInfo


class DeviceBackend(BaseIOSBackend):
    """Backend for USB-connected iOS devices."""

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
        clear_text=True,
        ui_tree=True,
        check_screen=True,
        back=True,
        home=True,
    )

    def __init__(self) -> None:
        super().__init__(runtime="device")

    def list_targets(self) -> list[IOSTargetInfo]:
        return [
            IOSTargetInfo(
                target_id=info.device_id,
                runtime=self.runtime,
                status=info.status,
                model=info.model,
                os_version=info.ios_version,
                name=info.model,
                metadata={"source": "tidevice"},
            )
            for info in list_devices()
        ]

    def get_screen_size(self, target_id: str | None = None) -> tuple[int, int]:
        client = get_wda_client(target_id)
        window_size = client.window_size()
        width = window_size.width if hasattr(window_size, "width") else window_size[0]
        height = window_size.height if hasattr(window_size, "height") else window_size[1]
        return int(width), int(height)

    def launch_app(
        self,
        app_name: str | None = None,
        bundle_id: str | None = None,
        app_path: str | None = None,
        target_id: str | None = None,
    ) -> bool:
        if app_path:
            raise self._unsupported("launch_app_with_app_path")

        resolved_bundle_id = bundle_id or (get_package_name(app_name) if app_name else None)
        if not resolved_bundle_id:
            return False

        client = get_wda_client(target_id)
        client.app_launch(resolved_bundle_id)
        time.sleep(2.0)
        return True

    def get_current_app(self, target_id: str | None = None) -> str:
        return device_get_current_app(device_id=target_id)

    def get_screenshot(self, target_id: str | None = None) -> Screenshot:
        return get_screenshot(device_id=target_id)

    def tap(self, x: int, y: int, target_id: str | None = None) -> None:
        device_tap(x, y, device_id=target_id)

    def double_tap(self, x: int, y: int, target_id: str | None = None) -> None:
        device_double_tap(x, y, device_id=target_id)

    def long_press(
        self,
        x: int,
        y: int,
        duration_ms: int = 3000,
        target_id: str | None = None,
    ) -> None:
        device_long_press(x, y, duration_ms=duration_ms, device_id=target_id)

    def swipe(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        duration_ms: int | None = None,
        target_id: str | None = None,
    ) -> None:
        device_swipe(
            start_x,
            start_y,
            end_x,
            end_y,
            duration_ms=duration_ms,
            device_id=target_id,
        )

    def type_text(self, text: str, target_id: str | None = None) -> None:
        input_type_text(text, device_id=target_id)

    def clear_text(self, target_id: str | None = None) -> None:
        input_clear_text(device_id=target_id)

    def back(self, target_id: str | None = None) -> None:
        device_back(device_id=target_id)

    def home(self, target_id: str | None = None) -> None:
        device_home(device_id=target_id)

    def ui_tree(self, target_id: str | None = None) -> dict[str, Any]:
        client = get_wda_client(target_id)
        xml_str = client.source(format="xml")
        return {"elements": _parse_ios_ui_xml(xml_str)}

    def app_state(
        self,
        bundle_id: str | None = None,
        target_id: str | None = None,
    ) -> dict[str, Any]:
        current_bundle_id = _get_current_bundle_id(target_id)
        if bundle_id:
            matched = current_bundle_id == bundle_id
            return {
                "bundle_id": bundle_id,
                "current_bundle_id": current_bundle_id,
                "running": matched,
                "foreground": matched,
                "resumed": matched,
            }

        active = bool(current_bundle_id and current_bundle_id != "com.apple.springboard")
        return {
            "bundle_id": current_bundle_id,
            "current_bundle_id": current_bundle_id,
            "running": active,
            "foreground": active,
            "resumed": active,
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

        raise TimeoutError(
            f"Timed out waiting for {bundle_id} to reach state: {state}"
        )

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


def _parse_ios_ui_xml(xml_str: str) -> list[dict[str, Any]]:
    """Parse WDA accessibility XML into a JSON-friendly element list."""

    elements: list[dict[str, Any]] = []
    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError:
        return elements

    for node in root.iter():
        if node.tag in ("AppiumAUT", "hierarchy"):
            continue
        elem = {
            "type": node.get("type", node.tag),
            "name": node.get("name", ""),
            "label": node.get("label", ""),
            "value": node.get("value", ""),
            "visible": node.get("visible", ""),
            "enabled": node.get("enabled", ""),
            "x": node.get("x", ""),
            "y": node.get("y", ""),
            "width": node.get("width", ""),
            "height": node.get("height", ""),
        }
        if elem["name"] or elem["label"] or elem["value"] or elem["type"]:
            elements.append(elem)
    return elements


def _get_current_bundle_id(target_id: str | None) -> str:
    """Return the current foreground bundle ID, if available."""

    client = get_wda_client(target_id)
    try:
        app_info = client.app_current()
    except Exception:
        return ""

    if isinstance(app_info, dict):
        return app_info.get("bundleId", "")
    return getattr(app_info, "bundleId", "")
