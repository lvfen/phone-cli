"""超时回收看门狗。"""
import logging
import threading
from typing import Callable
from phone_cli.daemon.session import SessionManager
from phone_cli.daemon.device import DeviceManager

logger = logging.getLogger(__name__)

class TimeoutWatchdog:
    """定期扫描活跃会话，过期空闲会话并释放设备。"""
    def __init__(self, session_mgr: SessionManager, device_mgr: DeviceManager,
                 check_interval: float = 10.0, on_expire: Callable[[str], None] | None = None) -> None:
        self._session_mgr = session_mgr
        self._device_mgr = device_mgr
        self._check_interval = check_interval
        self._on_expire = on_expire
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=self._check_interval + 1)
        self._thread = None

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            self._stop_event.wait(timeout=self._check_interval)
            if self._stop_event.is_set():
                break
            try:
                self._check_expired()
            except Exception:
                logger.exception("Watchdog check failed")

    def _check_expired(self) -> None:
        expired = self._session_mgr.find_expired()
        for session in expired:
            self._session_mgr.expire(session.session_id)
            if session.device_id:
                self._device_mgr.release_session(session.device_id)
            logger.info("Session %s expired (device=%s)", session.session_id, session.device_id)
            if self._on_expire:
                self._on_expire(session.session_id)
