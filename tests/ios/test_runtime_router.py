from unittest.mock import MagicMock, patch

import pytest

from phone_cli import ios
from phone_cli.ios.runtime.app_on_mac_backend import AppOnMacBackend
from phone_cli.ios.runtime.device_backend import DeviceBackend
from phone_cli.ios.runtime.router import get_backend, normalize_runtime, resolve_runtime
from phone_cli.ios.runtime.simulator_backend import SimulatorBackend


def test_normalize_runtime_accepts_cli_style_name():
    assert normalize_runtime("app-on-mac") == "app_on_mac"


def test_normalize_runtime_rejects_unknown_value():
    with pytest.raises(ValueError):
        normalize_runtime("unknown")


def test_resolve_runtime_prefers_explicit_override():
    state = {"ios_runtime": "device"}
    assert resolve_runtime(runtime="simulator", state=state) == "simulator"


def test_resolve_runtime_uses_state_when_present():
    state = {"ios_runtime": "app_on_mac"}
    assert resolve_runtime(state=state) == "app_on_mac"


def test_get_backend_defaults_to_device():
    backend = get_backend()
    assert isinstance(backend, DeviceBackend)


def test_get_backend_from_state_returns_expected_backend():
    backend = get_backend(state={"ios_runtime": "app_on_mac"})
    assert isinstance(backend, AppOnMacBackend)


def test_get_backend_explicit_runtime_returns_expected_backend():
    backend = get_backend(runtime="simulator")
    assert isinstance(backend, SimulatorBackend)


def test_ios_facade_list_devices_routes_through_backend():
    backend = MagicMock()
    backend.list_targets.return_value = []
    with patch("phone_cli.ios.get_backend", return_value=backend) as mock_get_backend:
        result = ios.list_devices(runtime="simulator")
    assert result == []
    mock_get_backend.assert_called_once_with(runtime="simulator", state=None)
    backend.list_targets.assert_called_once_with()
