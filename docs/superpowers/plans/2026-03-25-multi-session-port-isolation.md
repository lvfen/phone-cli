# 多会话端口隔离实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用全局中央守护进程替代现有的 per-device-type daemon 架构，支持多 AI 会话并行操控设备，动态端口分配，会话超时管理。

**Architecture:** 新建 `phone_cli/daemon/` 模块，包含 server（主循环）、session（会话管理）、device（设备管理+端口分配）、watchdog（超时回收）、protocol（IPC 协议）。新建 `phone_cli/client.py` 作为 AI 会话的轻量客户端。现有 `adb/connection.py`、`hdc/connection.py`、`ios/connection.py` 不变，被 DeviceManager 内部调用。

**Tech Stack:** Python 3.12+, threading, socket (Unix domain), subprocess, pytest, unittest.mock

**Spec:** `docs/superpowers/specs/2026-03-25-multi-session-port-isolation-design.md`

---

## File Structure

```
phone_cli/
├── daemon/
│   ├── __init__.py              # 新建: 包导出
│   ├── server.py                # 新建: DaemonServer 主循环，PID/socket 生命周期
│   ├── session.py               # 新建: SessionManager, Session dataclass
│   ├── device.py                # 新建: DeviceManager, DeviceSlot, 端口分配
│   ├── watchdog.py              # 新建: TimeoutWatchdog
│   └── protocol.py              # 新建: IPC 协议，命令分发
├── client.py                    # 新建: PhoneClient
├── config/
│   └── ports.py                 # 新建: 端口范围常量，is_port_available()
├── cli/
│   ├── daemon.py                # 修改: 迁移到新架构（后续 Task）
│   ├── main.py                  # 修改: CLI 入口适配新 daemon
│   └── commands.py              # 修改: 命令通过新 daemon 分发
tests/
├── daemon/
│   ├── __init__.py
│   ├── test_session.py          # 新建
│   ├── test_device.py           # 新建
│   ├── test_watchdog.py         # 新建
│   ├── test_protocol.py         # 新建
│   └── test_server.py           # 新建
├── test_ports.py                # 新建
└── test_client.py               # 新建
```

---

### Task 1: 端口配置与检测工具

**Files:**
- Create: `phone_cli/config/ports.py`
- Test: `tests/test_ports.py`

- [ ] **Step 1: 编写端口检测的失败测试**

```python
# tests/test_ports.py
import socket
from unittest.mock import patch

from phone_cli.config.ports import (
    PORT_RANGES,
    PortExhaustedError,
    is_port_available,
)


def test_port_ranges_defined():
    assert "wda" in PORT_RANGES
    assert "adb" in PORT_RANGES
    assert "hdc" in PORT_RANGES
    assert PORT_RANGES["wda"] == (8100, 8200)
    assert PORT_RANGES["adb"] == (5037, 5100)
    assert PORT_RANGES["hdc"] == (5100, 5200)


def test_is_port_available_free_port():
    # 端口 0 让 OS 分配一个空闲端口，然后关闭，再检测该端口应该可用
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    # socket 已关闭，端口应可用
    assert is_port_available(port) is True


def test_is_port_available_occupied_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        # socket 仍然打开，端口被占用
        assert is_port_available(port) is False
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /Users/longquan/development/code/phone-cli && python -m pytest tests/test_ports.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'phone_cli.config.ports'`

- [ ] **Step 3: 实现端口配置模块**

```python
# phone_cli/config/ports.py
"""端口范围常量与端口可用性检测工具。"""

import socket

# 端口范围定义: (起始端口, 结束端口)，左闭右开
PORT_RANGES: dict[str, tuple[int, int]] = {
    "wda": (8100, 8200),   # iOS WDA proxy
    "adb": (5037, 5100),   # ADB server
    "hdc": (5100, 5200),   # HDC server
}


class PortExhaustedError(Exception):
    """端口范围内所有端口均被占用。"""


def is_port_available(port: int) -> bool:
    """检测端口是否可用。

    使用 bind 检测，能捕获所有被占用状态（包括 TIME_WAIT）。

    Args:
        port: 要检测的端口号。

    Returns:
        True 如果端口可用，False 如果被占用。
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /Users/longquan/development/code/phone-cli && python -m pytest tests/test_ports.py -v`
Expected: 3 PASSED

- [ ] **Step 5: 提交**

```bash
cd /Users/longquan/development/code/phone-cli
git add phone_cli/config/ports.py tests/test_ports.py
git commit -m "feat: add port range config and availability check utility"
```

---

### Task 2: SessionManager — 会话生命周期管理

**Files:**
- Create: `phone_cli/daemon/__init__.py`
- Create: `phone_cli/daemon/session.py`
- Test: `tests/daemon/__init__.py`
- Test: `tests/daemon/test_session.py`

- [ ] **Step 1: 编写会话创建/激活/释放的失败测试**

```python
# tests/daemon/test_session.py
import time

from phone_cli.daemon.session import Session, SessionManager


class TestSessionCreate:
    def test_create_active_session(self):
        mgr = SessionManager()
        session = mgr.create("ios", device_id="iPhone-A", timeout=300)
        assert session.status == "active"
        assert session.device_type == "ios"
        assert session.device_id == "iPhone-A"
        assert session.session_id  # UUID 不为空

    def test_create_queued_session(self):
        mgr = SessionManager()
        session = mgr.create("ios", device_id=None, timeout=300, status="queued")
        assert session.status == "queued"
        assert session.device_id is None


class TestSessionRelease:
    def test_release_active_session(self):
        mgr = SessionManager()
        session = mgr.create("ios", device_id="iPhone-A")
        mgr.release(session.session_id)
        assert mgr.get(session.session_id).status == "released"

    def test_release_unknown_session_returns_none(self):
        mgr = SessionManager()
        result = mgr.release("nonexistent-id")
        assert result is None


class TestSessionExpire:
    def test_expire_session(self):
        mgr = SessionManager()
        session = mgr.create("ios", device_id="iPhone-A")
        mgr.expire(session.session_id)
        assert mgr.get(session.session_id).status == "expired"


class TestSessionActivity:
    def test_touch_updates_last_active(self):
        mgr = SessionManager()
        session = mgr.create("ios", device_id="iPhone-A")
        old_ts = session.last_active_at
        time.sleep(0.01)
        mgr.touch(session.session_id)
        assert mgr.get(session.session_id).last_active_at > old_ts


class TestSessionQuery:
    def test_active_sessions(self):
        mgr = SessionManager()
        s1 = mgr.create("ios", device_id="iPhone-A")
        s2 = mgr.create("adb", device_id="emu-5554")
        mgr.release(s1.session_id)
        active = mgr.active_sessions()
        assert len(active) == 1
        assert active[0].session_id == s2.session_id

    def test_expired_sessions_for_timeout(self):
        mgr = SessionManager()
        s1 = mgr.create("ios", device_id="iPhone-A", timeout=0.01)
        time.sleep(0.02)
        expired = mgr.find_expired()
        assert len(expired) == 1
        assert expired[0].session_id == s1.session_id
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /Users/longquan/development/code/phone-cli && python -m pytest tests/daemon/test_session.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 实现 SessionManager**

```python
# phone_cli/daemon/__init__.py
"""Central daemon for multi-session device management."""

# phone_cli/daemon/session.py
"""会话生命周期管理。"""

import threading
import time
import uuid
from dataclasses import dataclass, field


@dataclass
class Session:
    session_id: str
    device_type: str
    device_id: str | None
    status: str  # "active" | "queued" | "released" | "expired"
    timeout: float
    created_at: float = field(default_factory=time.time)
    acquired_at: float = 0.0
    last_active_at: float = field(default_factory=time.time)


class SessionManager:
    """管理所有 AI 会话的生命周期。线程安全。"""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()

    def create(
        self,
        device_type: str,
        device_id: str | None = None,
        timeout: float = 300,
        status: str = "active",
    ) -> Session:
        """创建新会话。"""
        now = time.time()
        session = Session(
            session_id=str(uuid.uuid4()),
            device_type=device_type,
            device_id=device_id,
            status=status,
            timeout=timeout,
            created_at=now,
            acquired_at=now if status == "active" else 0.0,
            last_active_at=now,
        )
        with self._lock:
            self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str) -> Session | None:
        """获取会话。"""
        with self._lock:
            return self._sessions.get(session_id)

    def release(self, session_id: str) -> Session | None:
        """释放会话。"""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            session.status = "released"
            return session

    def expire(self, session_id: str) -> Session | None:
        """标记会话超时。"""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            session.status = "expired"
            return session

    def activate(self, session_id: str, device_id: str) -> Session | None:
        """将排队会话激活。"""
        now = time.time()
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            session.status = "active"
            session.device_id = device_id
            session.acquired_at = now
            session.last_active_at = now
            return session

    def touch(self, session_id: str) -> None:
        """刷新会话活跃时间。"""
        with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session.last_active_at = time.time()

    def active_sessions(self) -> list[Session]:
        """返回所有活跃会话。"""
        with self._lock:
            return [s for s in self._sessions.values() if s.status == "active"]

    def find_expired(self) -> list[Session]:
        """查找所有应该过期的活跃会话。"""
        now = time.time()
        with self._lock:
            return [
                s
                for s in self._sessions.values()
                if s.status == "active"
                and (now - s.last_active_at) > s.timeout
            ]
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /Users/longquan/development/code/phone-cli && python -m pytest tests/daemon/test_session.py -v`
Expected: ALL PASSED

- [ ] **Step 5: 提交**

```bash
cd /Users/longquan/development/code/phone-cli
git add phone_cli/daemon/__init__.py phone_cli/daemon/session.py tests/daemon/__init__.py tests/daemon/test_session.py
git commit -m "feat: add SessionManager with lifecycle management"
```

---

### Task 3: DeviceManager — 设备管理与端口分配

**Files:**
- Create: `phone_cli/daemon/device.py`
- Test: `tests/daemon/test_device.py`

- [ ] **Step 1: 编写端口分配和设备槽管理的失败测试**

```python
# tests/daemon/test_device.py
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
        # 占用 8100
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", 8100))
            port = DeviceManager().allocate_port("wda")
            assert port == 8101

    def test_allocate_skips_internally_assigned(self):
        mgr = DeviceManager()
        # 模拟 8100 已分配给另一个设备
        mgr._assigned_ports.add(8100)
        port = mgr.allocate_port("wda")
        assert port == 8101

    def test_allocate_raises_when_exhausted(self):
        mgr = DeviceManager()
        # 标记所有 wda 端口为已分配
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
        slot = mgr.create_slot("iPhone-A", "ios", port=8100)
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
        # 没有 slot → 所有已发现的设备都是空闲的
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
        # iPhone-A 有 slot 但无会话（空闲热连接）
        mgr.create_slot("iPhone-A", "ios", port=8100)
        result = mgr.find_free_device(["iPhone-A", "iPhone-B"])
        # 优先复用已有连接
        assert result == "iPhone-A"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /Users/longquan/development/code/phone-cli && python -m pytest tests/daemon/test_device.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 实现 DeviceManager**

```python
# phone_cli/daemon/device.py
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


_DISCOVER_FNS = {
    "adb": adb_list_devices,
    "hdc": hdc_list_devices,
    "ios": ios_list_devices,
}


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

    # ── 端口分配 ──

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
        raise PortExhaustedError(
            f"No available port in range {start}-{end} for {port_type}"
        )

    def release_port(self, port: int) -> None:
        """释放已分配的端口。"""
        with self._lock:
            self._assigned_ports.discard(port)

    # ── DeviceSlot 管理 ──

    def create_slot(
        self, device_id: str, device_type: str, port: int
    ) -> DeviceSlot:
        """创建设备槽。"""
        slot = DeviceSlot(
            device_id=device_id,
            device_type=device_type,
            port=port,
        )
        with self._lock:
            self._slots[device_id] = slot
        return slot

    def get_slot(self, device_id: str) -> DeviceSlot | None:
        """获取设备槽。"""
        with self._lock:
            return self._slots.get(device_id)

    def remove_slot(self, device_id: str) -> DeviceSlot | None:
        """移除设备槽并释放端口。"""
        with self._lock:
            slot = self._slots.pop(device_id, None)
        if slot:
            self.release_port(slot.port)
        return slot

    def assign_session(self, device_id: str, session_id: str) -> None:
        """将会话分配给设备。"""
        with self._lock:
            slot = self._slots.get(device_id)
            if slot:
                slot.current_session_id = session_id

    def release_session(self, device_id: str) -> str | None:
        """释放设备上的当前会话，返回 wait_queue 中下一个 session_id（如果有）。"""
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
        """将会话加入设备等待队列，返回队列位置。"""
        with self._lock:
            slot = self._slots.get(device_id)
            if slot:
                slot.wait_queue.append(session_id)
                return len(slot.wait_queue)
        return -1

    # ── 设备发现 ──

    def discover(self, device_type: str) -> list[Any]:
        """发现指定类型的设备，带缓存。"""
        now = time.time()
        cached = self._discovery_cache.get(device_type)
        if cached and (now - cached[0]) < self._cache_ttl:
            return cached[1]

        fn = _DISCOVER_FNS.get(device_type)
        if fn is None:
            return []
        try:
            devices = fn()
        except Exception:
            devices = []
        self._discovery_cache[device_type] = (now, devices)
        return devices

    # ── 设备调度 ──

    def find_free_device(self, discovered_ids: list[str]) -> str | None:
        """从已发现设备中找到一个空闲的。

        优先级：
        1. 有 slot 且无会话（热连接复用）
        2. 无 slot（新设备）
        3. 全部被占 → None
        """
        idle_with_slot = []
        no_slot = []
        with self._lock:
            for device_id in discovered_ids:
                slot = self._slots.get(device_id)
                if slot is None:
                    no_slot.append(device_id)
                elif slot.current_session_id is None:
                    idle_with_slot.append(device_id)
                # else: occupied, skip

        if idle_with_slot:
            return idle_with_slot[0]
        if no_slot:
            return no_slot[0]
        return None

    def find_shortest_queue_device(self, discovered_ids: list[str]) -> str | None:
        """找到等待队列最短的设备（用于排队）。"""
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
        """返回所有设备槽（快照）。"""
        with self._lock:
            return list(self._slots.values())
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /Users/longquan/development/code/phone-cli && python -m pytest tests/daemon/test_device.py -v`
Expected: ALL PASSED

- [ ] **Step 5: 提交**

```bash
cd /Users/longquan/development/code/phone-cli
git add phone_cli/daemon/device.py tests/daemon/test_device.py
git commit -m "feat: add DeviceManager with port allocation and device scheduling"
```

---

### Task 4: TimeoutWatchdog — 超时回收

**Files:**
- Create: `phone_cli/daemon/watchdog.py`
- Test: `tests/daemon/test_watchdog.py`

- [ ] **Step 1: 编写 watchdog 的失败测试**

```python
# tests/daemon/test_watchdog.py
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

        watchdog = TimeoutWatchdog(
            session_mgr, device_mgr,
            check_interval=0.02,
            on_expire=on_expire,
        )
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

        watchdog = TimeoutWatchdog(
            session_mgr, device_mgr,
            check_interval=0.02,
            on_expire=on_expire,
        )
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
        watchdog.stop()  # 不应报错
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /Users/longquan/development/code/phone-cli && python -m pytest tests/daemon/test_watchdog.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 实现 TimeoutWatchdog**

```python
# phone_cli/daemon/watchdog.py
"""超时回收看门狗。"""

import logging
import threading
from typing import Callable

from phone_cli.daemon.session import SessionManager
from phone_cli.daemon.device import DeviceManager

logger = logging.getLogger(__name__)


class TimeoutWatchdog:
    """定期扫描活跃会话，过期空闲会话并释放设备。"""

    def __init__(
        self,
        session_mgr: SessionManager,
        device_mgr: DeviceManager,
        check_interval: float = 10.0,
        on_expire: Callable[[str], None] | None = None,
    ) -> None:
        self._session_mgr = session_mgr
        self._device_mgr = device_mgr
        self._check_interval = check_interval
        self._on_expire = on_expire
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """启动后台巡检线程。"""
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """停止巡检。"""
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
            logger.info(
                "Session %s expired (device=%s)",
                session.session_id,
                session.device_id,
            )
            if self._on_expire:
                self._on_expire(session.session_id)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /Users/longquan/development/code/phone-cli && python -m pytest tests/daemon/test_watchdog.py -v`
Expected: ALL PASSED

- [ ] **Step 5: 提交**

```bash
cd /Users/longquan/development/code/phone-cli
git add phone_cli/daemon/watchdog.py tests/daemon/test_watchdog.py
git commit -m "feat: add TimeoutWatchdog for idle session expiry"
```

---

### Task 5: IPC 协议与命令分发

**Files:**
- Create: `phone_cli/daemon/protocol.py`
- Test: `tests/daemon/test_protocol.py`

- [ ] **Step 1: 编写协议解析和命令分发的失败测试**

```python
# tests/daemon/test_protocol.py
import json

from phone_cli.daemon.protocol import (
    parse_request,
    ok_response,
    error_response,
    Request,
)


class TestParseRequest:
    def test_valid_request(self):
        raw = json.dumps({"cmd": "acquire", "args": {"device_type": "ios"}})
        req = parse_request(raw)
        assert req.cmd == "acquire"
        assert req.args == {"device_type": "ios"}

    def test_missing_cmd(self):
        raw = json.dumps({"args": {}})
        req = parse_request(raw)
        assert req is None

    def test_invalid_json(self):
        req = parse_request("not json")
        assert req is None

    def test_args_default_empty(self):
        raw = json.dumps({"cmd": "status"})
        req = parse_request(raw)
        assert req.args == {}


class TestResponses:
    def test_ok_response(self):
        resp = ok_response({"session_id": "abc"})
        parsed = json.loads(resp)
        assert parsed["ok"] is True
        assert parsed["session_id"] == "abc"

    def test_ok_response_empty(self):
        resp = ok_response()
        parsed = json.loads(resp)
        assert parsed["ok"] is True

    def test_error_response(self):
        resp = error_response("session_not_found", "Unknown session")
        parsed = json.loads(resp)
        assert parsed["ok"] is False
        assert parsed["error"] == "session_not_found"
        assert parsed["msg"] == "Unknown session"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /Users/longquan/development/code/phone-cli && python -m pytest tests/daemon/test_protocol.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 实现协议模块**

```python
# phone_cli/daemon/protocol.py
"""IPC 协议定义：请求解析、响应构建、命令分发。"""

import json
from dataclasses import dataclass


@dataclass
class Request:
    cmd: str
    args: dict


def parse_request(raw: str) -> Request | None:
    """解析 JSON 请求字符串。"""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    cmd = data.get("cmd")
    if not cmd:
        return None
    return Request(cmd=cmd, args=data.get("args", {}))


def ok_response(data: dict | None = None) -> str:
    """构建成功响应。"""
    resp = {"ok": True}
    if data:
        resp.update(data)
    return json.dumps(resp, ensure_ascii=False)


def error_response(error: str, msg: str) -> str:
    """构建错误响应。"""
    return json.dumps(
        {"ok": False, "error": error, "msg": msg},
        ensure_ascii=False,
    )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /Users/longquan/development/code/phone-cli && python -m pytest tests/daemon/test_protocol.py -v`
Expected: ALL PASSED

- [ ] **Step 5: 提交**

```bash
cd /Users/longquan/development/code/phone-cli
git add phone_cli/daemon/protocol.py tests/daemon/test_protocol.py
git commit -m "feat: add IPC protocol with request parsing and response builders"
```

---

### Task 6: DaemonServer — 守护进程主循环

**Files:**
- Create: `phone_cli/daemon/server.py`
- Test: `tests/daemon/test_server.py`

- [ ] **Step 1: 编写 server 生命周期和命令处理的失败测试**

```python
# tests/daemon/test_server.py
import json
import os
import socket
import tempfile
import threading
import time

from phone_cli.daemon.server import DaemonServer


class TestDaemonLifecycle:
    def test_start_creates_pid_and_socket(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            server = DaemonServer(home_dir=tmpdir)
            t = threading.Thread(target=server.run_foreground)
            t.daemon = True
            t.start()
            time.sleep(0.3)

            assert os.path.exists(server.pid_path)
            assert os.path.exists(server.socket_path)

            server.shutdown()
            t.join(timeout=2)

    def test_shutdown_removes_pid_and_socket(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            server = DaemonServer(home_dir=tmpdir)
            t = threading.Thread(target=server.run_foreground)
            t.daemon = True
            t.start()
            time.sleep(0.3)

            server.shutdown()
            t.join(timeout=2)

            assert not os.path.exists(server.pid_path)
            assert not os.path.exists(server.socket_path)

    def test_stale_pid_cleaned_on_start(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pid_path = os.path.join(tmpdir, "phone-cli.pid")
            with open(pid_path, "w") as f:
                f.write("99999999")  # 不存在的 PID

            server = DaemonServer(home_dir=tmpdir)
            t = threading.Thread(target=server.run_foreground)
            t.daemon = True
            t.start()
            time.sleep(0.3)

            # 应该成功启动（清理了残留 PID）
            assert os.path.exists(server.pid_path)
            with open(server.pid_path) as f:
                assert f.read().strip() == str(os.getpid())

            server.shutdown()
            t.join(timeout=2)


class TestDaemonIPC:
    def test_status_command(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            server = DaemonServer(home_dir=tmpdir)
            t = threading.Thread(target=server.run_foreground)
            t.daemon = True
            t.start()
            time.sleep(0.3)

            # 发送 status 命令
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect(server.socket_path)
            sock.sendall(json.dumps({"cmd": "status"}).encode())
            sock.shutdown(socket.SHUT_WR)
            data = sock.recv(65536).decode()
            sock.close()

            resp = json.loads(data)
            assert resp["ok"] is True

            server.shutdown()
            t.join(timeout=2)

    def test_invalid_command(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            server = DaemonServer(home_dir=tmpdir)
            t = threading.Thread(target=server.run_foreground)
            t.daemon = True
            t.start()
            time.sleep(0.3)

            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect(server.socket_path)
            sock.sendall(json.dumps({"cmd": "bogus"}).encode())
            sock.shutdown(socket.SHUT_WR)
            data = sock.recv(65536).decode()
            sock.close()

            resp = json.loads(data)
            assert resp["ok"] is False
            assert resp["error"] == "invalid_request"

            server.shutdown()
            t.join(timeout=2)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /Users/longquan/development/code/phone-cli && python -m pytest tests/daemon/test_server.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 实现 DaemonServer**

```python
# phone_cli/daemon/server.py
"""守护进程主循环：PID/socket 管理，accept loop，命令分发。"""

import json
import logging
import os
import signal
import socket
import threading
import time
from typing import Any

from phone_cli.daemon.device import DeviceManager
from phone_cli.daemon.protocol import error_response, ok_response, parse_request
from phone_cli.daemon.session import SessionManager
from phone_cli.daemon.watchdog import TimeoutWatchdog
from phone_cli.config.ports import is_port_available

logger = logging.getLogger(__name__)


class DaemonServer:
    """中央守护进程。"""

    def __init__(self, home_dir: str = "~/.phone-cli") -> None:
        self.home_dir = os.path.expanduser(home_dir)
        os.makedirs(self.home_dir, exist_ok=True)

        self.pid_path = os.path.join(self.home_dir, "phone-cli.pid")
        self.socket_path = os.path.join(self.home_dir, "phone-cli.sock")

        self.session_mgr = SessionManager()
        self.device_mgr = DeviceManager()
        self.watchdog = TimeoutWatchdog(
            self.session_mgr, self.device_mgr,
            on_expire=self._on_session_expire,
        )

        self._stop_event = threading.Event()
        self._server_socket: socket.socket | None = None

        self._handlers: dict[str, Any] = {
            "status": self._cmd_status,
            "acquire": self._cmd_acquire,
            "operate": self._cmd_operate,
            "release": self._cmd_release,
            "heartbeat": self._cmd_heartbeat,
            "list_devices": self._cmd_list_devices,
        }

    # ── 生命周期 ──

    def run_foreground(self) -> None:
        """前台运行守护进程（阻塞直到 shutdown）。"""
        self._cleanup_stale()
        self._write_pid()

        # 注册 SIGTERM 处理（仅主线程）
        if threading.current_thread() is threading.main_thread():
            signal.signal(signal.SIGTERM, lambda *_: self.shutdown())

        self.watchdog.start()
        self._run_socket_server()

    def shutdown(self) -> None:
        """优雅关闭。"""
        self._stop_event.set()
        if self._server_socket:
            try:
                self._server_socket.close()
            except OSError:
                pass
        self.watchdog.stop()
        # 终止所有设备子进程：SIGTERM → 等 5s → SIGKILL
        for slot in self.device_mgr.all_slots():
            if slot.process and slot.process.poll() is None:
                slot.process.terminate()
        for slot in self.device_mgr.all_slots():
            if slot.process and slot.process.poll() is None:
                try:
                    slot.process.wait(timeout=5)
                except Exception:
                    slot.process.kill()
        self._cleanup_files()

    # ── Socket 服务器 ──

    def _run_socket_server(self) -> None:
        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)

        self._server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server_socket.bind(self.socket_path)
        self._server_socket.listen(10)
        self._server_socket.settimeout(1.0)

        while not self._stop_event.is_set():
            try:
                conn, _ = self._server_socket.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(
                target=self._handle_connection,
                args=(conn,),
                daemon=True,
            ).start()

    def _handle_connection(self, conn: socket.socket) -> None:
        try:
            data = conn.recv(65536).decode("utf-8")
            if not data:
                return
            response = self._dispatch(data)
            conn.sendall(response.encode("utf-8"))
        except Exception:
            logger.exception("Error handling connection")
        finally:
            conn.close()

    def _dispatch(self, raw: str) -> str:
        req = parse_request(raw)
        if req is None:
            return error_response("invalid_request", "Malformed request")
        handler = self._handlers.get(req.cmd)
        if handler is None:
            return error_response("invalid_request", f"Unknown command: {req.cmd}")
        try:
            return handler(req.args)
        except Exception as e:
            logger.exception("Command %s failed", req.cmd)
            return error_response("operation_failed", str(e))

    # ── 命令处理 ──

    def _cmd_status(self, args: dict) -> str:
        sessions = [
            {
                "session_id": s.session_id,
                "device_id": s.device_id,
                "device_type": s.device_type,
                "status": s.status,
                "idle_seconds": round(
                    time.time() - s.last_active_at, 1
                ),
            }
            for s in self.session_mgr.active_sessions()
        ]
        devices = [
            {
                "device_id": slot.device_id,
                "device_type": slot.device_type,
                "port": slot.port,
                "status": "occupied" if slot.current_session_id else "idle",
            }
            for slot in self.device_mgr.all_slots()
        ]
        return ok_response({"sessions": sessions, "devices": devices})

    def _cmd_acquire(self, args: dict) -> str:
        device_type = args.get("device_type")
        if not device_type:
            return error_response("invalid_request", "device_type is required")
        timeout = float(args.get("timeout", 300))

        # 1. 发现设备
        discovered = self.device_mgr.discover(device_type)
        if not discovered:
            return error_response(
                "no_device_available",
                f"No {device_type} devices found",
            )
        discovered_ids = [d.device_id for d in discovered]

        # 2. 找空闲设备
        free_id = self.device_mgr.find_free_device(discovered_ids)
        if free_id:
            slot = self.device_mgr.get_slot(free_id)
            if slot is None:
                port = self.device_mgr.allocate_port(
                    self._port_type(device_type)
                )
                slot = self.device_mgr.create_slot(free_id, device_type, port)
            session = self.session_mgr.create(
                device_type, device_id=free_id, timeout=timeout
            )
            self.device_mgr.assign_session(free_id, session.session_id)
            return ok_response({
                "session_id": session.session_id,
                "status": "active",
                "device_id": free_id,
                "device_type": device_type,
                "port": slot.port,
            })

        # 3. 全忙 → 排队（非阻塞，返回 queued 状态）
        # 注意：spec 中描述了阻塞式 acquire（daemon 保持连接不关闭），
        # 但 v1 实现采用非阻塞方式：立即返回 queued 状态，
        # 会话在设备释放时自动激活。客户端可通过轮询 status 检查激活状态。
        # 阻塞式 acquire 可在后续版本中实现。
        queue_device = self.device_mgr.find_shortest_queue_device(discovered_ids)
        if not queue_device:
            return error_response("no_device_available", "No devices to queue on")
        session = self.session_mgr.create(
            device_type, device_id=None, timeout=timeout, status="queued"
        )
        pos = self.device_mgr.enqueue_session(queue_device, session.session_id)
        return ok_response({
            "session_id": session.session_id,
            "status": "queued",
            "queue_position": pos,
        })

    def _cmd_operate(self, args: dict) -> str:
        session_id = args.get("session_id")
        session = self.session_mgr.get(session_id) if session_id else None
        if not session:
            return error_response("session_not_found", "Unknown session")
        if session.status == "expired":
            return error_response("session_expired", "Session has expired")
        if session.status != "active":
            return error_response("session_not_found", f"Session status: {session.status}")
        self.session_mgr.touch(session_id)
        # TODO: 实际设备操作在 Task 8 中实现
        action = args.get("action", "")
        return ok_response({"action": action, "result": {}})

    def _cmd_release(self, args: dict) -> str:
        session_id = args.get("session_id")
        session = self.session_mgr.release(session_id) if session_id else None
        if not session:
            return error_response("session_not_found", "Unknown session")
        if session.device_id:
            next_sid = self.device_mgr.release_session(session.device_id)
            # 激活排队的下一个会话
            if next_sid:
                self.session_mgr.activate(next_sid, session.device_id)
        return ok_response({"released": True})

    def _cmd_heartbeat(self, args: dict) -> str:
        session_id = args.get("session_id")
        session = self.session_mgr.get(session_id) if session_id else None
        if not session:
            return error_response("session_not_found", "Unknown session")
        self.session_mgr.touch(session_id)
        return ok_response({"alive": True})

    def _cmd_list_devices(self, args: dict) -> str:
        device_type = args.get("device_type")
        if not device_type:
            return error_response("invalid_request", "device_type is required")
        discovered = self.device_mgr.discover(device_type)
        devices = [
            {"device_id": d.device_id, "status": getattr(d, "status", "unknown")}
            for d in discovered
        ]
        return ok_response({"devices": devices})

    # ── 内部 ──

    @staticmethod
    def _port_type(device_type: str) -> str:
        return {"ios": "wda", "adb": "adb", "hdc": "hdc"}[device_type]

    def _on_session_expire(self, session_id: str) -> None:
        """watchdog 回调：会话过期时，激活排队的下一个会话。"""
        session = self.session_mgr.get(session_id)
        if session and session.device_id:
            next_sid = self.device_mgr.release_session(session.device_id)
            if next_sid:
                self.session_mgr.activate(next_sid, session.device_id)

    def _cleanup_stale(self) -> None:
        # 1. 清理残留 PID
        if os.path.exists(self.pid_path):
            try:
                with open(self.pid_path) as f:
                    pid = int(f.read().strip())
                os.kill(pid, 0)
                # 进程存活 → daemon 已运行
                raise RuntimeError(f"Daemon already running (pid={pid})")
            except (ProcessLookupError, PermissionError, ValueError):
                os.remove(self.pid_path)
        # 2. 清理残留 socket
        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)
        # 3. 清理孤儿子进程（已知端口范围）
        self._kill_orphan_processes()

    def _kill_orphan_processes(self) -> None:
        """扫描已知端口范围，终止孤儿 adb server / wdaproxy 进程。"""
        import subprocess as sp
        # 清理孤儿 adb server
        for port in range(5037, 5100):
            if not is_port_available(port):
                try:
                    sp.run(["adb", "-P", str(port), "kill-server"],
                           capture_output=True, timeout=3)
                except Exception:
                    pass
        # 清理孤儿 wdaproxy / hdc — 通过 lsof 查找端口占用进程
        for port_start, port_end in [(8100, 8200), (5100, 5200)]:
            for port in range(port_start, port_end):
                if not is_port_available(port):
                    try:
                        result = sp.run(
                            ["lsof", "-ti", f":{port}"],
                            capture_output=True, text=True, timeout=3,
                        )
                        for pid_str in result.stdout.strip().split("\n"):
                            if pid_str.strip():
                                os.kill(int(pid_str.strip()), signal.SIGTERM)
                    except Exception:
                        pass

    def _write_pid(self) -> None:
        with open(self.pid_path, "w") as f:
            f.write(str(os.getpid()))

    def _cleanup_files(self) -> None:
        for path in [self.pid_path, self.socket_path]:
            if os.path.exists(path):
                os.remove(path)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /Users/longquan/development/code/phone-cli && python -m pytest tests/daemon/test_server.py -v`
Expected: ALL PASSED

- [ ] **Step 5: 提交**

```bash
cd /Users/longquan/development/code/phone-cli
git add phone_cli/daemon/server.py tests/daemon/test_server.py
git commit -m "feat: add DaemonServer with socket IPC and command handlers"
```

---

### Task 7: PhoneClient — AI 会话客户端

**Files:**
- Create: `phone_cli/client.py`
- Test: `tests/test_client.py`

- [ ] **Step 1: 编写客户端的失败测试**

```python
# tests/test_client.py
import json
import os
import socket
import tempfile
import threading
import time

from phone_cli.client import PhoneClient
from phone_cli.daemon.server import DaemonServer


def _start_server(tmpdir: str) -> tuple[DaemonServer, threading.Thread]:
    server = DaemonServer(home_dir=tmpdir)
    t = threading.Thread(target=server.run_foreground, daemon=True)
    t.start()
    time.sleep(0.3)
    return server, t


class TestPhoneClientAcquireRelease:
    def test_acquire_and_release(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            server, t = _start_server(tmpdir)
            try:
                client = PhoneClient(socket_path=server.socket_path)
                # acquire 在没有设备时应返回 no_device_available
                resp = client.acquire(device_type="adb")
                assert resp["ok"] is False
                assert resp["error"] == "no_device_available"
            finally:
                server.shutdown()
                t.join(timeout=2)


class TestPhoneClientHeartbeat:
    def test_heartbeat_unknown_session(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            server, t = _start_server(tmpdir)
            try:
                client = PhoneClient(socket_path=server.socket_path)
                resp = client.heartbeat()
                assert resp["ok"] is False
                assert resp["error"] == "session_not_found"
            finally:
                server.shutdown()
                t.join(timeout=2)


class TestPhoneClientStatus:
    def test_status(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            server, t = _start_server(tmpdir)
            try:
                client = PhoneClient(socket_path=server.socket_path)
                resp = client.status()
                assert resp["ok"] is True
                assert "sessions" in resp
                assert "devices" in resp
            finally:
                server.shutdown()
                t.join(timeout=2)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /Users/longquan/development/code/phone-cli && python -m pytest tests/test_client.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 实现 PhoneClient**

```python
# phone_cli/client.py
"""AI 会话轻量客户端，通过 Unix socket 与守护进程通信。"""

import json
import os
import socket


class PhoneClient:
    """AI 会话通过此客户端与守护进程通信。"""

    def __init__(
        self,
        socket_path: str = "~/.phone-cli/phone-cli.sock",
        timeout: float = 15.0,
    ) -> None:
        self._socket_path = os.path.expanduser(socket_path)
        self._timeout = timeout
        self._session_id: str | None = None

    def acquire(
        self,
        device_type: str,
        timeout: float = 300,
        wait: bool = True,
    ) -> dict:
        """申请指定类型的设备。"""
        resp = self._send("acquire", device_type=device_type, timeout=timeout)
        if resp.get("ok") and resp.get("session_id"):
            self._session_id = resp["session_id"]
        return resp

    def release(self) -> dict:
        """释放设备。"""
        resp = self._send("release", session_id=self._session_id)
        self._session_id = None
        return resp

    def heartbeat(self) -> dict:
        """保持活跃。"""
        return self._send("heartbeat", session_id=self._session_id)

    def status(self) -> dict:
        """查询守护进程状态。"""
        return self._send("status")

    def list_devices(self, device_type: str) -> dict:
        """发现可用设备。"""
        return self._send("list_devices", device_type=device_type)

    def operate(self, action: str, **kwargs) -> dict:
        """执行设备操作。"""
        return self._send(
            "operate", session_id=self._session_id, action=action, **kwargs
        )

    def tap(self, x: int, y: int) -> dict:
        return self.operate("tap", x=x, y=y)

    def swipe(
        self, x1: int, y1: int, x2: int, y2: int, duration: int = 300
    ) -> dict:
        return self.operate(
            "swipe", x1=x1, y1=y1, x2=x2, y2=y2, duration=duration
        )

    def screenshot(self, path: str | None = None) -> dict:
        return self.operate("screenshot", path=path)

    @property
    def session_id(self) -> str | None:
        return self._session_id

    def _send(self, cmd: str, **args) -> dict:
        """发送命令到守护进程。"""
        payload = json.dumps({"cmd": cmd, "args": args})
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self._timeout)
        try:
            sock.connect(self._socket_path)
            sock.sendall(payload.encode("utf-8"))
            sock.shutdown(socket.SHUT_WR)
            chunks: list[bytes] = []
            while True:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)
            return json.loads(b"".join(chunks).decode("utf-8"))
        except ConnectionRefusedError:
            return {"ok": False, "error": "daemon_not_running", "msg": "Cannot connect to daemon"}
        except socket.timeout:
            return {"ok": False, "error": "timeout", "msg": "Request timed out"}
        finally:
            sock.close()
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /Users/longquan/development/code/phone-cli && python -m pytest tests/test_client.py -v`
Expected: ALL PASSED

- [ ] **Step 5: 提交**

```bash
cd /Users/longquan/development/code/phone-cli
git add phone_cli/client.py tests/test_client.py
git commit -m "feat: add PhoneClient for AI session communication"
```

---

### Task 8: Server 集成 — 设备操作路由

**Files:**
- Modify: `phone_cli/daemon/server.py` — 完善 `_cmd_operate` 中的设备操作路由
- Test: `tests/daemon/test_server_operate.py`

说明：此任务将 `_cmd_operate` 中的 TODO 替换为真实的设备操作路由，复用现有的 `phone_cli/cli/commands.py` 中的 `_call_device_method` 模式。

- [ ] **Step 1: 编写设备操作路由的失败测试**

```python
# tests/daemon/test_server_operate.py
import json
import os
import socket
import tempfile
import threading
import time
from unittest.mock import MagicMock, patch

from phone_cli.daemon.server import DaemonServer


def _start_server(tmpdir):
    server = DaemonServer(home_dir=tmpdir)
    t = threading.Thread(target=server.run_foreground, daemon=True)
    t.start()
    time.sleep(0.3)
    return server, t


def _ipc(socket_path, cmd, args=None):
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(socket_path)
    sock.sendall(json.dumps({"cmd": cmd, "args": args or {}}).encode())
    sock.shutdown(socket.SHUT_WR)
    data = sock.recv(65536).decode()
    sock.close()
    return json.loads(data)


class TestOperateRouting:
    @patch("phone_cli.daemon.device.adb_list_devices")
    def test_tap_routes_to_adb(self, mock_list):
        mock_list.return_value = [MagicMock(device_id="emu-5554", status="device")]
        with tempfile.TemporaryDirectory() as tmpdir:
            server, t = _start_server(tmpdir)
            try:
                # acquire
                resp = _ipc(server.socket_path, "acquire", {"device_type": "adb"})
                assert resp["ok"] is True
                sid = resp["session_id"]

                # operate tap (实际设备不存在，但路由应该到达)
                with patch("phone_cli.daemon.server.DaemonServer._execute_device_action") as mock_exec:
                    mock_exec.return_value = {"tapped": True}
                    resp = _ipc(server.socket_path, "operate", {
                        "session_id": sid,
                        "action": "tap",
                        "x": 100,
                        "y": 200,
                    })
                    assert resp["ok"] is True
                    mock_exec.assert_called_once()
            finally:
                server.shutdown()
                t.join(timeout=2)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /Users/longquan/development/code/phone-cli && python -m pytest tests/daemon/test_server_operate.py -v`
Expected: FAIL — `_execute_device_action` 不存在

- [ ] **Step 3: 在 DaemonServer 中实现设备操作路由**

在 `phone_cli/daemon/server.py` 中**替换** Task 6 中的 `_cmd_operate` 方法（移除 TODO 版本），并新增 `_execute_device_action` 方法：

```python
# 添加到 DaemonServer 类中

def _cmd_operate(self, args: dict) -> str:
    session_id = args.get("session_id")
    session = self.session_mgr.get(session_id) if session_id else None
    if not session:
        return error_response("session_not_found", "Unknown session")
    if session.status == "expired":
        return error_response("session_expired", "Session has expired")
    if session.status != "active":
        return error_response("session_not_found", f"Session status: {session.status}")
    self.session_mgr.touch(session_id)

    action = args.get("action", "")
    slot = self.device_mgr.get_slot(session.device_id) if session.device_id else None
    if not slot:
        return error_response("device_disconnected", "Device slot not found")

    # 在设备锁内串行执行
    with slot.lock:
        try:
            result = self._execute_device_action(
                slot, session, action, args
            )
            return ok_response({"action": action, "result": result})
        except Exception as e:
            return error_response("operation_failed", str(e))

def _execute_device_action(
    self, slot: "DeviceSlot", session: "Session", action: str, args: dict
) -> dict:
    """将操作路由到对应平台模块。"""
    device_type = slot.device_type
    device_id = slot.device_id

    if device_type == "adb":
        from phone_cli import adb
        module = adb
    elif device_type == "hdc":
        from phone_cli import hdc
        module = hdc
    elif device_type == "ios":
        from phone_cli import ios
        module = ios
    else:
        raise ValueError(f"Unknown device type: {device_type}")

    method = getattr(module, action, None)
    if method is None:
        raise ValueError(f"Unknown action: {action} for {device_type}")

    # 提取操作参数（排除 session_id 和 action）
    op_args = {k: v for k, v in args.items() if k not in ("session_id", "action")}
    result = method(device_id=device_id, **op_args)
    return result if isinstance(result, dict) else {"raw": result}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /Users/longquan/development/code/phone-cli && python -m pytest tests/daemon/test_server_operate.py -v`
Expected: ALL PASSED

- [ ] **Step 5: 提交**

```bash
cd /Users/longquan/development/code/phone-cli
git add phone_cli/daemon/server.py tests/daemon/test_server_operate.py
git commit -m "feat: add device operation routing in DaemonServer"
```

---

### Task 9: 集成测试 — 完整 acquire-operate-release 流程

**Files:**
- Test: `tests/daemon/test_integration.py`

- [ ] **Step 1: 编写端到端集成测试**

```python
# tests/daemon/test_integration.py
"""集成测试：通过 PhoneClient 和真实 DaemonServer 验证完整流程。"""

import tempfile
import threading
import time
from unittest.mock import MagicMock, patch

from phone_cli.client import PhoneClient
from phone_cli.daemon.server import DaemonServer


def _start_server(tmpdir):
    server = DaemonServer(home_dir=tmpdir)
    t = threading.Thread(target=server.run_foreground, daemon=True)
    t.start()
    time.sleep(0.3)
    return server, t


class TestFullLifecycle:
    @patch("phone_cli.daemon.device.adb_list_devices")
    def test_acquire_operate_release(self, mock_list):
        mock_list.return_value = [MagicMock(device_id="emu-5554", status="device")]
        with tempfile.TemporaryDirectory() as tmpdir:
            server, t = _start_server(tmpdir)
            try:
                client = PhoneClient(socket_path=server.socket_path)

                # acquire
                resp = client.acquire(device_type="adb")
                assert resp["ok"] is True
                assert resp["status"] == "active"
                assert resp["device_id"] == "emu-5554"
                assert client.session_id is not None

                # status 应显示 1 个活跃会话
                status = client.status()
                assert len(status["sessions"]) == 1

                # release
                resp = client.release()
                assert resp["ok"] is True

                # status 应显示 0 个活跃会话
                status = client.status()
                assert len(status["sessions"]) == 0
            finally:
                server.shutdown()
                t.join(timeout=2)

    @patch("phone_cli.daemon.device.adb_list_devices")
    def test_multiple_sessions_different_devices(self, mock_list):
        mock_list.return_value = [
            MagicMock(device_id="emu-5554", status="device"),
            MagicMock(device_id="emu-5556", status="device"),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            server, t = _start_server(tmpdir)
            try:
                client1 = PhoneClient(socket_path=server.socket_path)
                client2 = PhoneClient(socket_path=server.socket_path)

                resp1 = client1.acquire(device_type="adb")
                resp2 = client2.acquire(device_type="adb")

                assert resp1["ok"] is True
                assert resp2["ok"] is True
                assert resp1["device_id"] != resp2["device_id"]

                # 各自使用不同端口
                assert resp1["port"] != resp2["port"]

                client1.release()
                client2.release()
            finally:
                server.shutdown()
                t.join(timeout=2)

    @patch("phone_cli.daemon.device.adb_list_devices")
    def test_queue_when_all_busy(self, mock_list):
        mock_list.return_value = [MagicMock(device_id="emu-5554", status="device")]
        with tempfile.TemporaryDirectory() as tmpdir:
            server, t = _start_server(tmpdir)
            try:
                client1 = PhoneClient(socket_path=server.socket_path)
                client2 = PhoneClient(socket_path=server.socket_path)

                resp1 = client1.acquire(device_type="adb")
                assert resp1["ok"] is True
                assert resp1["status"] == "active"

                # 第二个客户端 → 排队
                resp2 = client2.acquire(device_type="adb")
                assert resp2["ok"] is True
                assert resp2["status"] == "queued"
            finally:
                server.shutdown()
                t.join(timeout=2)

    @patch("phone_cli.daemon.device.adb_list_devices")
    def test_session_timeout_expiry(self, mock_list):
        mock_list.return_value = [MagicMock(device_id="emu-5554", status="device")]
        with tempfile.TemporaryDirectory() as tmpdir:
            server = DaemonServer(home_dir=tmpdir)
            server.watchdog = __import__(
                "phone_cli.daemon.watchdog", fromlist=["TimeoutWatchdog"]
            ).TimeoutWatchdog(
                server.session_mgr, server.device_mgr, check_interval=0.05
            )
            t = threading.Thread(target=server.run_foreground, daemon=True)
            t.start()
            time.sleep(0.3)
            try:
                client = PhoneClient(socket_path=server.socket_path)
                resp = client.acquire(device_type="adb", timeout=0.1)
                assert resp["ok"] is True
                sid = resp["session_id"]

                # 等待超时
                time.sleep(0.3)

                # 操作应返回 expired
                resp = client.operate("tap", x=100, y=200)
                assert resp["ok"] is False
                assert resp["error"] == "session_expired"
            finally:
                server.shutdown()
                t.join(timeout=2)

    @patch("phone_cli.daemon.device.adb_list_devices")
    def test_concurrent_acquire_no_duplicate_ports(self, mock_list):
        """多线程并发 acquire 不应分配重复端口。"""
        mock_list.return_value = [
            MagicMock(device_id=f"emu-{i}", status="device")
            for i in range(10)
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            server, t = _start_server(tmpdir)
            try:
                results = []
                errors = []

                def _acquire(idx):
                    try:
                        client = PhoneClient(socket_path=server.socket_path)
                        resp = client.acquire(device_type="adb")
                        results.append(resp)
                    except Exception as e:
                        errors.append(e)

                threads = [threading.Thread(target=_acquire, args=(i,)) for i in range(5)]
                for th in threads:
                    th.start()
                for th in threads:
                    th.join(timeout=5)

                assert not errors
                active = [r for r in results if r.get("status") == "active"]
                ports = [r["port"] for r in active]
                device_ids = [r["device_id"] for r in active]
                # 端口不重复
                assert len(ports) == len(set(ports))
                # 设备不重复
                assert len(device_ids) == len(set(device_ids))
            finally:
                server.shutdown()
                t.join(timeout=2)

    @patch("phone_cli.daemon.device.adb_list_devices")
    def test_queue_activation_after_release(self, mock_list):
        """释放设备后，排队会话应被激活。"""
        mock_list.return_value = [MagicMock(device_id="emu-5554", status="device")]
        with tempfile.TemporaryDirectory() as tmpdir:
            server, t = _start_server(tmpdir)
            try:
                client1 = PhoneClient(socket_path=server.socket_path)
                client2 = PhoneClient(socket_path=server.socket_path)

                # client1 获取设备
                resp1 = client1.acquire(device_type="adb")
                assert resp1["status"] == "active"

                # client2 排队
                resp2 = client2.acquire(device_type="adb")
                assert resp2["status"] == "queued"
                queued_sid = resp2["session_id"]

                # client1 释放
                client1.release()

                # 验证排队会话已被激活
                session = server.session_mgr.get(queued_sid)
                assert session.status == "active"
                assert session.device_id == "emu-5554"
            finally:
                server.shutdown()
                t.join(timeout=2)
```

- [ ] **Step 2: 运行测试**

Run: `cd /Users/longquan/development/code/phone-cli && python -m pytest tests/daemon/test_integration.py -v`
Expected: ALL PASSED

- [ ] **Step 3: 提交**

```bash
cd /Users/longquan/development/code/phone-cli
git add tests/daemon/test_integration.py
git commit -m "test: add integration tests for full session lifecycle"
```

---

### Task 10: CLI 入口适配

**Files:**
- Modify: `phone_cli/cli/main.py` — 新增 `phone-cli daemon` 子命令组
- Test: 通过现有 CLI 测试验证不破坏现有功能

- [ ] **Step 1: 在 main.py 中新增 daemon 子命令**

在现有 `cli` group 下新增 `daemon` 子命令组：

```python
# 在 phone_cli/cli/main.py 中新增

@cli.group()
def daemon():
    """Central daemon management."""
    pass

@daemon.command("start")
@click.option("--foreground", is_flag=True, help="Run in foreground")
def daemon_start(foreground):
    """Start the central daemon."""
    from phone_cli.daemon.server import DaemonServer
    server = DaemonServer()
    if foreground:
        server.run_foreground()
    else:
        # TODO: background fork（复用现有 _run_background 模式）
        click.echo("Background daemon start not yet implemented")

@daemon.command("stop")
def daemon_stop():
    """Stop the central daemon."""
    import os, signal
    pid_path = os.path.expanduser("~/.phone-cli/phone-cli.pid")
    if not os.path.exists(pid_path):
        click.echo("Daemon not running")
        return
    with open(pid_path) as f:
        pid = int(f.read().strip())
    try:
        os.kill(pid, signal.SIGTERM)
        click.echo(f"Daemon stopped (pid={pid})")
    except ProcessLookupError:
        click.echo("Daemon not running (stale PID)")
        os.remove(pid_path)

@daemon.command("status")
def daemon_status():
    """Show daemon status."""
    from phone_cli.client import PhoneClient
    client = PhoneClient()
    resp = client.status()
    click.echo(json.dumps(resp, indent=2, ensure_ascii=False))
```

- [ ] **Step 2: 运行现有 CLI 测试确认不破坏**

Run: `cd /Users/longquan/development/code/phone-cli && python -m pytest tests/cli/ -v --ignore=tests/cli/test_e2e.py`
Expected: ALL PASSED（现有测试不受影响）

- [ ] **Step 3: 提交**

```bash
cd /Users/longquan/development/code/phone-cli
git add phone_cli/cli/main.py
git commit -m "feat: add 'phone-cli daemon' CLI subcommands"
```

---

### Task 11: 全量测试验证

- [ ] **Step 1: 运行所有新增单元测试**

Run: `cd /Users/longquan/development/code/phone-cli && python -m pytest tests/test_ports.py tests/daemon/ tests/test_client.py -v`
Expected: ALL PASSED

- [ ] **Step 2: 运行所有现有测试确认无回归**

Run: `cd /Users/longquan/development/code/phone-cli && python -m pytest tests/cli/ -v --ignore=tests/cli/test_e2e.py`
Expected: ALL PASSED

- [ ] **Step 3: 提交最终状态（如有需要）**

如果有任何修复，提交：
```bash
git add -A && git commit -m "fix: address test issues from full verification"
```
