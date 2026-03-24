import json
from unittest.mock import MagicMock, patch

from phone_cli.ios.host.permissions import (
    HostAutomationSupport,
    PermissionStatus,
)
from phone_cli.ios.runtime.discovery import (
    RuntimeCandidate,
    RuntimeDiscoveryResult,
    detect_app_on_mac_candidates,
    detect_device_candidates,
    detect_simulator_candidates,
    resolve_runtime_selection,
)


def test_resolve_runtime_selection_with_no_candidates():
    result = RuntimeDiscoveryResult(candidates=[], reasons=[])
    outcome = resolve_runtime_selection(result)
    assert outcome.mode == "unavailable"
    assert outcome.error_code == "NO_AVAILABLE_IOS_RUNTIME"


def test_resolve_runtime_selection_with_single_candidate():
    result = RuntimeDiscoveryResult(
        candidates=[
            RuntimeCandidate(
                runtime="device",
                target_id="udid-1",
                label="Test iPhone",
            )
        ],
        reasons=[],
    )
    outcome = resolve_runtime_selection(result)
    assert outcome.mode == "auto_selected"
    assert outcome.candidate is not None
    assert outcome.candidate.target_id == "udid-1"


def test_resolve_runtime_selection_with_multiple_candidates():
    result = RuntimeDiscoveryResult(
        candidates=[
            RuntimeCandidate(runtime="device", target_id="udid-1", label="iPhone"),
            RuntimeCandidate(runtime="simulator", target_id="sim-1", label="Simulator"),
        ],
        reasons=[],
    )
    outcome = resolve_runtime_selection(result)
    assert outcome.mode == "selection_required"
    assert outcome.error_code == "RUNTIME_SELECTION_REQUIRED"


def test_detect_device_candidates_empty_list():
    completed = MagicMock(returncode=0, stdout="[]", stderr="")
    with patch("subprocess.run", return_value=completed):
        candidates, reasons = detect_device_candidates()
    assert candidates == []
    assert reasons[0].code == "no_connected_devices"


def test_detect_simulator_candidates_filters_booted_devices():
    payload = {
        "devices": {
            "com.apple.CoreSimulator.SimRuntime.iOS-18-2": [
                {
                    "name": "iPhone 16 Pro",
                    "udid": "sim-1",
                    "state": "Booted",
                    "isAvailable": True,
                },
                {
                    "name": "iPhone 15",
                    "udid": "sim-2",
                    "state": "Shutdown",
                    "isAvailable": True,
                },
            ]
        }
    }
    completed = MagicMock(
        returncode=0,
        stdout=json.dumps(payload),
        stderr="",
    )
    with patch("subprocess.run", return_value=completed):
        candidates, reasons = detect_simulator_candidates()
    assert reasons == []
    assert len(candidates) == 1
    assert candidates[0].runtime == "simulator"
    assert candidates[0].target_id == "sim-1"


def test_detect_app_on_mac_candidates_from_supported_host():
    support = HostAutomationSupport(
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
    with patch(
        "phone_cli.ios.host.permissions.check_app_on_mac_host_support",
        return_value=support,
    ):
        candidates, reasons = detect_app_on_mac_candidates()
    assert reasons == []
    assert len(candidates) == 1
    assert candidates[0].runtime == "app_on_mac"
    assert candidates[0].target_id == "local-mac"
