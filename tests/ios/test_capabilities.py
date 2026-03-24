import pytest

from phone_cli.ios.runtime.app_on_mac_backend import AppOnMacBackend
from phone_cli.ios.runtime.device_backend import DeviceBackend
from phone_cli.ios.runtime.simulator_backend import SimulatorBackend
from phone_cli.ios.runtime.base import UnsupportedOperationError


def test_device_backend_reports_supported_capabilities():
    capabilities = DeviceBackend().get_capabilities()
    assert capabilities["launch"] is True
    assert capabilities["app_state"] is True
    assert capabilities["wait_for_app"] is True
    assert capabilities["screenshot"] is True
    assert capabilities["tap"] is True
    assert capabilities["type"] is True
    assert capabilities["ui_tree"] is True
    assert capabilities["check_screen"] is True
    assert capabilities["install"] is False
    assert capabilities["app_log"] is False


def test_simulator_backend_reports_stub_capabilities():
    capabilities = SimulatorBackend().get_capabilities()
    assert capabilities["launch"] is True
    assert capabilities["app_state"] is True
    assert capabilities["wait_for_app"] is True
    assert capabilities["screenshot"] is True
    assert capabilities["tap"] is True
    assert capabilities["type"] is True
    assert capabilities["check_screen"] is True
    assert capabilities["ui_tree"] is False


def test_app_on_mac_backend_reports_stub_capabilities():
    capabilities = AppOnMacBackend().get_capabilities()
    assert capabilities["launch"] is True
    assert capabilities["get_current_app"] is True
    assert capabilities["app_state"] is True
    assert capabilities["wait_for_app"] is True
    assert capabilities["screenshot"] is True
    assert capabilities["tap"] is True
    assert capabilities["type"] is True
    assert capabilities["ui_tree"] is True
    assert capabilities["check_screen"] is True


def test_simulator_backend_requires_target_for_launch():
    backend = SimulatorBackend()
    with pytest.raises(RuntimeError):
        backend.launch_app(bundle_id="com.example.demo")
