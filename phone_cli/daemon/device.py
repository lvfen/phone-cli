"""设备管理与端口分配。"""
import threading
import time
from dataclasses import dataclass, field
from subprocess import Popen
from typing import Any
from phone_cli.config.ports import PORT_RANGES, PortExhaustedError, is_port_available


def adb_list_devices():
    from phone_cli.adb.connection import list_devices
    return list_devices()


def hdc_list_devices():
    from phone_cli.hdc.connection import list_devices
    return list_devices()


def ios_list_devices():
    from phone_cli.ios.connection import list_devices
    return list_devices()


_DISCOVER_FNS = {"adb": "adb_list_devices", "hdc": "hdc_list_devices", "ios": "ios_list_devices"}


@dataclass
class DeviceSlot:
    device_id: str
    device_type: str
    port: int
    current_session_id: str | None = None
    wait_queue: list[str] = field(default_factory=list)
    process: Popen | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)
    connected_at: float = field(default_factory=time.time)


class DeviceManager:
    """管理所有设备的连接、端口和生命周期。线程安全。"""

    def __init__(self) -> None:
        self._slots: dict[str, DeviceSlot] = {}
        self._assigned_ports: set[int] = set()
        self._lock = threading.Lock()
        self._discovery_cache: dict[str, tuple[float, list[Any]]] = {}
        self._cache_ttl = 10.0

    def allocate_port(self, port_type: str) -> int:
        """从指定范围分配一个可用端口。线程安全。"""
        start, end = PORT_RANGES[port_type]
        with self._lock:
            for port in range(start, end):
                if port in self._assigned_ports:
                    continue
                if not is_port_available(port):
                    continue
                self._assigned_ports.add(port)
                return port
        raise PortExhaustedError(f"No available port in range {start}-{end} for {port_type}")

    def release_port(self, port: int) -> None:
        with self._lock:
            self._assigned_ports.discard(port)

    def create_slot(self, device_id: str, device_type: str, port: int) -> DeviceSlot:
        slot = DeviceSlot(device_id=device_id, device_type=device_type, port=port)
        with self._lock:
            self._slots[device_id] = slot
        return slot

    def get_slot(self, device_id: str) -> DeviceSlot | None:
        with self._lock:
            return self._slots.get(device_id)

    def remove_slot(self, device_id: str) -> DeviceSlot | None:
        with self._lock:
            slot = self._slots.pop(device_id, None)
        if slot:
            self.release_port(slot.port)
        return slot

    def assign_session(self, device_id: str, session_id: str) -> None:
        with self._lock:
            slot = self._slots.get(device_id)
            if slot:
                slot.current_session_id = session_id

    def release_session(self, device_id: str) -> str | None:
        with self._lock:
            slot = self._slots.get(device_id)
            if not slot:
                return None
            slot.current_session_id = None
            if slot.wait_queue:
                next_session_id = slot.wait_queue.pop(0)
                slot.current_session_id = next_session_id
                return next_session_id
            return None

    def enqueue_session(self, device_id: str, session_id: str) -> int:
        with self._lock:
            slot = self._slots.get(device_id)
            if slot:
                slot.wait_queue.append(session_id)
                return len(slot.wait_queue)
        return -1

    def discover(self, device_type: str) -> list[Any]:
        now = time.time()
        cached = self._discovery_cache.get(device_type)
        if cached and (now - cached[0]) < self._cache_ttl:
            return cached[1]
        fn_name = _DISCOVER_FNS.get(device_type)
        if fn_name is None:
            return []
        import phone_cli.daemon.device as _self_module
        fn = getattr(_self_module, fn_name, None)
        if fn is None:
            return []
        try:
            devices = fn()
        except Exception:
            devices = []
        self._discovery_cache[device_type] = (now, devices)
        return devices

    def find_free_device(self, discovered_ids: list[str]) -> str | None:
        idle_with_slot = []
        no_slot = []
        with self._lock:
            for device_id in discovered_ids:
                slot = self._slots.get(device_id)
                if slot is None:
                    no_slot.append(device_id)
                elif slot.current_session_id is None:
                    idle_with_slot.append(device_id)
        if idle_with_slot:
            return idle_with_slot[0]
        if no_slot:
            return no_slot[0]
        return None

    def find_shortest_queue_device(self, discovered_ids: list[str]) -> str | None:
        best_id = None
        best_len = float("inf")
        with self._lock:
            for device_id in discovered_ids:
                slot = self._slots.get(device_id)
                if slot:
                    qlen = len(slot.wait_queue)
                    if qlen < best_len:
                        best_len = qlen
                        best_id = device_id
        return best_id

    def all_slots(self) -> list[DeviceSlot]:
        with self._lock:
            return list(self._slots.values())
