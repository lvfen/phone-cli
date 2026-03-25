import socket
import subprocess
import threading
from unittest.mock import MagicMock, patch
from phone_cli.config.ports import PortExhaustedError
from phone_cli.daemon.device import DeviceManager, DeviceSlot

class TestPortAllocation:
    def test_allocate_returns_default_port_first(self):
        mgr = DeviceManager()
        port = mgr.allocate_port("wda")
        assert port == 8100

    def test_allocate_skips_occupied_port(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", 8100))
            port = DeviceManager().allocate_port("wda")
            assert port == 8101

    def test_allocate_skips_internally_assigned(self):
        mgr = DeviceManager()
        mgr._assigned_ports.add(8100)
        port = mgr.allocate_port("wda")
        assert port == 8101

    def test_allocate_raises_when_exhausted(self):
        mgr = DeviceManager()
        for p in range(8100, 8200):
            mgr._assigned_ports.add(p)
        try:
            mgr.allocate_port("wda")
            assert False, "Should have raised PortExhaustedError"
        except PortExhaustedError:
            pass

class TestDeviceSlotManagement:
    def test_create_slot(self):
        mgr = DeviceManager()
        slot = mgr.create_slot("iPhone-A", "ios", port=8100)
        assert slot.device_id == "iPhone-A"
        assert slot.device_type == "ios"
        assert slot.port == 8100
        assert slot.current_session_id is None
        assert slot.wait_queue == []

    def test_get_slot(self):
        mgr = DeviceManager()
        mgr.create_slot("iPhone-A", "ios", port=8100)
        slot = mgr.get_slot("iPhone-A")
        assert slot is not None
        assert slot.device_id == "iPhone-A"

    def test_get_nonexistent_slot(self):
        mgr = DeviceManager()
        assert mgr.get_slot("nonexistent") is None

    def test_assign_session_to_slot(self):
        mgr = DeviceManager()
        mgr.create_slot("iPhone-A", "ios", port=8100)
        mgr.assign_session("iPhone-A", "session-1")
        slot = mgr.get_slot("iPhone-A")
        assert slot.current_session_id == "session-1"

    def test_release_slot(self):
        mgr = DeviceManager()
        mgr.create_slot("iPhone-A", "ios", port=8100)
        mgr.assign_session("iPhone-A", "session-1")
        mgr.release_session("iPhone-A")
        slot = mgr.get_slot("iPhone-A")
        assert slot.current_session_id is None

    def test_release_slot_frees_port(self):
        mgr = DeviceManager()
        mgr.create_slot("iPhone-A", "ios", port=8100)
        mgr.remove_slot("iPhone-A")
        assert 8100 not in mgr._assigned_ports

class TestDeviceDiscovery:
    @patch("phone_cli.daemon.device.adb_list_devices")
    def test_discover_adb_devices(self, mock_list):
        mock_list.return_value = [
            MagicMock(device_id="emulator-5554", status="device"),
            MagicMock(device_id="emulator-5556", status="device"),
        ]
        mgr = DeviceManager()
        devices = mgr.discover("adb")
        assert len(devices) == 2
        assert devices[0].device_id == "emulator-5554"

class TestFindFreeDevice:
    def test_find_free_when_new_device(self):
        mgr = DeviceManager()
        result = mgr.find_free_device(["iPhone-A", "iPhone-B"])
        assert result == "iPhone-A"

    def test_find_free_skips_occupied(self):
        mgr = DeviceManager()
        mgr.create_slot("iPhone-A", "ios", port=8100)
        mgr.assign_session("iPhone-A", "session-1")
        result = mgr.find_free_device(["iPhone-A", "iPhone-B"])
        assert result == "iPhone-B"

    def test_find_free_returns_none_all_occupied(self):
        mgr = DeviceManager()
        mgr.create_slot("iPhone-A", "ios", port=8100)
        mgr.assign_session("iPhone-A", "session-1")
        result = mgr.find_free_device(["iPhone-A"])
        assert result is None

    def test_find_free_prefers_existing_idle_slot(self):
        mgr = DeviceManager()
        mgr.create_slot("iPhone-A", "ios", port=8100)
        result = mgr.find_free_device(["iPhone-A", "iPhone-B"])
        assert result == "iPhone-A"
