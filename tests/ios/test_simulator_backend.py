import base64
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from phone_cli.ios.host.windows import HostWindow, Rect
from phone_cli.ios.runtime.base import UnsupportedOperationError
from phone_cli.ios.runtime.simulator_backend import SimulatorBackend


def _png_bytes(color: str = "black", size: tuple[int, int] = (20, 40)) -> bytes:
    image = Image.new("RGB", size, color=color)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_simulator_launch_app_tracks_pid():
    backend = SimulatorBackend()
    completed = MagicMock(stdout="com.example.demo: 4321")
    with patch.object(backend, "_run_simctl", return_value=completed):
        success = backend.launch_app(bundle_id="com.example.demo", target_id="sim-1")
    assert success is True
    assert backend._launched_pids["sim-1"]["com.example.demo"] == 4321
    assert backend._foreground_bundle_by_target["sim-1"] == "com.example.demo"


def test_simulator_app_state_uses_remembered_pid_when_listapps_unavailable():
    backend = SimulatorBackend()
    backend._launched_pids["sim-1"] = {"com.example.demo": 4321}
    backend._foreground_bundle_by_target["sim-1"] = "com.example.demo"
    with patch.object(backend, "_get_running_apps", return_value={}), \
         patch("phone_cli.ios.runtime.simulator_backend._pid_exists", return_value=True):
        state = backend.app_state(bundle_id="com.example.demo", target_id="sim-1")
    assert state["running"] is True
    assert state["foreground"] is True
    assert state["pid"] == 4321


def test_simulator_wait_for_app_polls_until_running():
    backend = SimulatorBackend()
    states = [
        {"running": False, "foreground": False},
        {"running": True, "foreground": True},
    ]
    with patch.object(backend, "app_state", side_effect=states):
        result = backend.wait_for_app(
            bundle_id="com.example.demo",
            timeout=5,
            state="running",
            target_id="sim-1",
        )
    assert result["running"] is True


def test_simulator_get_screenshot_decodes_png_dimensions():
    backend = SimulatorBackend()
    with patch.object(backend, "_capture_png_bytes", return_value=_png_bytes(size=(18, 36))):
        screenshot = backend.get_screenshot(target_id="sim-1")
    assert screenshot.width == 18
    assert screenshot.height == 36
    assert base64.b64decode(screenshot.base64_data)


def test_simulator_check_screen_reports_all_black():
    backend = SimulatorBackend()
    with patch.object(backend, "get_screenshot") as mock_get_screenshot:
        png_bytes = _png_bytes(color="black", size=(8, 8))
        mock_get_screenshot.return_value = MagicMock(
            base64_data=base64.b64encode(png_bytes).decode("utf-8")
        )
        result = backend.check_screen(target_id="sim-1")
    assert result["screen_state"] == "all_black"


def test_simulator_tap_maps_device_point_to_host_window():
    backend = SimulatorBackend()
    window = HostWindow(
        window_id=1,
        owner_name="Simulator",
        bundle_id="com.apple.iphonesimulator",
        title="iPhone 16 Pro",
        bounds=Rect(0, 0, 500, 900),
        render_bounds=Rect(10, 20, 400, 800),
    )
    with patch.object(backend, "_require_simulator_host_support"), \
         patch.object(backend, "_activate_simulator_application"), \
         patch.object(backend, "get_screen_size", return_value=(200, 400)), \
         patch("phone_cli.ios.runtime.simulator_backend._get_simulator_name", return_value="iPhone 16 Pro"), \
         patch("phone_cli.ios.runtime.simulator_backend.find_simulator_window", return_value=window), \
         patch("phone_cli.ios.runtime.simulator_backend.click_point") as mock_click:
        backend.tap(100, 200, target_id="sim-1")
    mock_click.assert_called_once_with(211, 421)


def test_simulator_ui_tree_is_unavailable():
    backend = SimulatorBackend()
    with pytest.raises(UnsupportedOperationError):
        backend.ui_tree(target_id="sim-1")
