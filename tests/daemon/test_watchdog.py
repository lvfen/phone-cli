import time
import threading
from unittest.mock import MagicMock, call
from phone_cli.daemon.session import SessionManager
from phone_cli.daemon.device import DeviceManager
from phone_cli.daemon.watchdog import TimeoutWatchdog

class TestWatchdogExpiry:
    def test_expires_idle_session(self):
        session_mgr = SessionManager()
        device_mgr = DeviceManager()
        on_expire = MagicMock()
        session = session_mgr.create("ios", device_id="iPhone-A", timeout=0.05)
        device_mgr.create_slot("iPhone-A", "ios", port=8100)
        device_mgr.assign_session("iPhone-A", session.session_id)
        watchdog = TimeoutWatchdog(session_mgr, device_mgr, check_interval=0.02, on_expire=on_expire)
        watchdog.start()
        time.sleep(0.15)
        watchdog.stop()
        assert session_mgr.get(session.session_id).status == "expired"
        on_expire.assert_called()

    def test_does_not_expire_active_session(self):
        session_mgr = SessionManager()
        device_mgr = DeviceManager()
        on_expire = MagicMock()
        session = session_mgr.create("ios", device_id="iPhone-A", timeout=1.0)
        device_mgr.create_slot("iPhone-A", "ios", port=8100)
        device_mgr.assign_session("iPhone-A", session.session_id)
        watchdog = TimeoutWatchdog(session_mgr, device_mgr, check_interval=0.02, on_expire=on_expire)
        watchdog.start()
        time.sleep(0.1)
        watchdog.stop()
        assert session_mgr.get(session.session_id).status == "active"
        on_expire.assert_not_called()

    def test_stop_is_idempotent(self):
        session_mgr = SessionManager()
        device_mgr = DeviceManager()
        watchdog = TimeoutWatchdog(session_mgr, device_mgr, check_interval=0.02)
        watchdog.start()
        watchdog.stop()
        watchdog.stop()  # should not error
