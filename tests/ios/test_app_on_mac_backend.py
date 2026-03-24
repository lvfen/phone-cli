import base64
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from phone_cli.ios.host.ax_tree import AXNode
from phone_cli.ios.host.permissions import (
    HostAutomationSupport,
    PermissionStatus,
)
from phone_cli.ios.host.screenshots import WindowScreenshot
from phone_cli.ios.host.windows import HostWindow, Rect
from phone_cli.ios.runtime.app_on_mac_backend import AppOnMacBackend


def _supported_host() -> HostAutomationSupport:
    return HostAutomationSupport(
        supported=True,
        platform="Darwin",
        machine="arm64",
        dependencies={
            "AppKit": "ok",
            "Quartz": "ok",
            "ApplicationServices": "ok",
        },
        accessibility=PermissionStatus(name="accessibility", state="granted"),
        screen_recording=PermissionStatus(name="screen_recording", state="granted"),
        reasons=[],
    )


def _png_bytes(color: str = "white", size: tuple[int, int] = (20, 30)) -> bytes:
    image = Image.new("RGB", size, color=color)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _window() -> HostWindow:
    return HostWindow(
        window_id=101,
        owner_name="Demo App",
        bundle_id="com.example.demo",
        title="Demo",
        bounds=Rect(10, 20, 400, 800),
        render_bounds=Rect(20, 40, 300, 600),
        pid=1234,
    )


def test_app_on_mac_launch_by_bundle_id_binds_window():
    backend = AppOnMacBackend()
    with patch("phone_cli.ios.runtime.app_on_mac_backend.check_app_on_mac_host_support", return_value=_supported_host()), \
         patch.object(backend, "_run_open") as mock_open, \
         patch("phone_cli.ios.runtime.app_on_mac_backend.find_app_window", return_value=_window()):
        success = backend.launch_app(bundle_id="com.example.demo", target_id="local-mac")
    assert success is True
    mock_open.assert_called_once_with(["open", "-b", "com.example.demo"])
    assert backend.get_bound_bundle_id("local-mac") == "com.example.demo"
    assert backend.get_bound_window_id("local-mac") == 101


def test_app_on_mac_get_current_app_maps_bundle_name():
    backend = AppOnMacBackend()
    with patch("phone_cli.ios.runtime.app_on_mac_backend._get_foreground_bundle_id", return_value="com.tencent.xin"):
        current = backend.get_current_app(target_id="local-mac")
    assert current == "微信"


def test_app_on_mac_get_current_app_prefers_bound_visible_bundle():
    backend = AppOnMacBackend()
    backend._bound_bundle_by_target["local-mac"] = "com.example.demo"
    with patch("phone_cli.ios.runtime.app_on_mac_backend._is_bundle_running", return_value=True), \
         patch.object(backend, "_resolve_bound_window", return_value=_window()), \
         patch("phone_cli.ios.runtime.app_on_mac_backend._get_foreground_bundle_id", return_value="com.apple.loginwindow"):
        current = backend.get_current_app(target_id="local-mac")
    assert current == "com.example.demo"


def test_app_on_mac_app_state_tracks_running_and_foreground():
    backend = AppOnMacBackend()
    backend._bound_bundle_by_target["local-mac"] = "com.example.demo"
    with patch("phone_cli.ios.runtime.app_on_mac_backend._get_foreground_bundle_id", return_value="com.example.demo"), \
         patch("phone_cli.ios.runtime.app_on_mac_backend._is_bundle_running", return_value=True), \
         patch.object(backend, "_bind_window", return_value=_window()):
        state = backend.app_state(target_id="local-mac")
    assert state["running"] is True
    assert state["foreground"] is True


def test_app_on_mac_app_state_treats_bound_window_as_ready():
    backend = AppOnMacBackend()
    backend._bound_bundle_by_target["local-mac"] = "com.example.demo"
    with patch("phone_cli.ios.runtime.app_on_mac_backend._get_foreground_bundle_id", return_value="com.other.app"), \
         patch("phone_cli.ios.runtime.app_on_mac_backend._is_bundle_running", return_value=True), \
         patch.object(backend, "_bind_window", return_value=_window()):
        state = backend.app_state(target_id="local-mac")
    assert state["current_bundle_id"] == "com.other.app"
    assert state["foreground"] is True
    assert state["window_ready"] is True


def test_app_on_mac_wait_for_app_polls_until_foreground():
    backend = AppOnMacBackend()
    states = [
        {"running": True, "foreground": False},
        {"running": True, "foreground": True},
    ]
    with patch.object(backend, "app_state", side_effect=states), \
         patch.object(backend, "_bind_window"), \
         patch("phone_cli.ios.runtime.app_on_mac_backend._activate_application") as mock_activate:
        result = backend.wait_for_app(
            bundle_id="com.example.demo",
            timeout=5,
            state="resumed",
            target_id="local-mac",
        )
    assert result["foreground"] is True
    mock_activate.assert_called_once_with("com.example.demo")


def test_app_on_mac_get_screenshot_uses_bound_window():
    backend = AppOnMacBackend()
    backend._bound_window_by_target["local-mac"] = 101
    with patch("phone_cli.ios.runtime.app_on_mac_backend.check_app_on_mac_host_support", return_value=_supported_host()), \
         patch("phone_cli.ios.runtime.app_on_mac_backend.get_window", return_value=_window()), \
         patch(
             "phone_cli.ios.runtime.app_on_mac_backend.capture_window",
             return_value=WindowScreenshot(window_id=101, png_bytes=_png_bytes(size=(12, 34))),
         ):
        screenshot = backend.get_screenshot(target_id="local-mac")
    assert screenshot.width == 12
    assert screenshot.height == 34


def test_app_on_mac_get_screenshot_rebinds_stale_window_to_expected_bundle():
    backend = AppOnMacBackend()
    backend._bound_bundle_by_target["local-mac"] = "com.example.demo"
    backend._bound_window_by_target["local-mac"] = 101
    stale_window = HostWindow(
        window_id=101,
        owner_name="Cursor",
        bundle_id="com.cursor.app",
        title="Wrong",
        bounds=Rect(0, 0, 1200, 800),
        render_bounds=Rect(0, 0, 1200, 800),
        pid=999,
    )
    rebound_window = HostWindow(
        window_id=202,
        owner_name="Demo App",
        bundle_id="com.example.demo",
        title="Demo",
        bounds=Rect(10, 20, 400, 800),
        render_bounds=Rect(20, 40, 300, 600),
        pid=1234,
    )
    with patch("phone_cli.ios.runtime.app_on_mac_backend.check_app_on_mac_host_support", return_value=_supported_host()), \
         patch("phone_cli.ios.runtime.app_on_mac_backend.get_window", return_value=stale_window), \
         patch("phone_cli.ios.runtime.app_on_mac_backend.find_app_window", return_value=rebound_window), \
         patch(
             "phone_cli.ios.runtime.app_on_mac_backend.capture_window",
             return_value=WindowScreenshot(window_id=202, png_bytes=_png_bytes(size=(16, 24))),
         ):
        screenshot = backend.get_screenshot(target_id="local-mac")
    assert screenshot.width == 16
    assert screenshot.height == 24
    assert backend.get_bound_window_id("local-mac") == 202


def test_app_on_mac_tap_maps_point_to_host_window():
    backend = AppOnMacBackend()
    backend._bound_window_by_target["local-mac"] = 101
    with patch("phone_cli.ios.runtime.app_on_mac_backend.check_app_on_mac_host_support", return_value=_supported_host()), \
         patch("phone_cli.ios.runtime.app_on_mac_backend.get_window", return_value=_window()), \
         patch("phone_cli.ios.runtime.app_on_mac_backend._activate_application"), \
         patch("phone_cli.ios.runtime.app_on_mac_backend.click_point") as mock_click:
        backend.tap(150, 300, target_id="local-mac")
    mock_click.assert_called_once_with(170, 340)


def test_app_on_mac_ui_tree_returns_root_and_elements():
    backend = AppOnMacBackend()
    backend._bound_window_by_target["local-mac"] = 101
    root = AXNode(
        role="Window",
        title="Demo",
        x=20,
        y=40,
        width=300,
        height=600,
        children=[AXNode(role="Button", title="Play")],
    )
    with patch("phone_cli.ios.runtime.app_on_mac_backend.check_app_on_mac_host_support", return_value=_supported_host()), \
         patch("phone_cli.ios.runtime.app_on_mac_backend.get_window", return_value=_window()), \
         patch("phone_cli.ios.runtime.app_on_mac_backend.read_window_tree", return_value=root):
        result = backend.ui_tree(target_id="local-mac")
    assert result["root"]["role"] == "Window"
    assert result["elements"][1]["role"] == "Button"


def test_app_on_mac_check_screen_reports_all_white():
    backend = AppOnMacBackend()
    with patch.object(backend, "get_screenshot") as mock_get_screenshot:
        png_bytes = _png_bytes(color="white", size=(8, 8))
        mock_get_screenshot.return_value = MagicMock(
            base64_data=base64.b64encode(png_bytes).decode("utf-8")
        )
        result = backend.check_screen(target_id="local-mac")
    assert result["screen_state"] == "all_white"
