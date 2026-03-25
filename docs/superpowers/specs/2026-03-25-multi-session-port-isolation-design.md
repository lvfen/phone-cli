# Multi-Session Port Isolation: Central Daemon Design

## Problem

phone-cli currently assigns fixed ports per platform (iOS WDA: 8100, ADB TCP: 5555, HDC TCP: 5555). When multiple AI sessions operate devices concurrently, port collisions and operation races make parallel automation impossible.

## Decision

Replace the per-device-type daemon instances with a single global daemon that owns all device connections, port allocation, and session lifecycle. AI sessions become stateless clients that acquire/release devices through the daemon.

## Architecture

```
AI Session 1 ──┐
AI Session 2 ──┤──▶ Central Daemon ──▶ Device A (iOS, port 8100)
AI Session 3 ──┘     (single process)  Device B (iOS, port 8101)
                                       Device C (Android, ADB server :5038)
```

### Why a Central Daemon

- All device operations run in one process: serial execution per device, no locks needed.
- Port allocation is process-internal: bind-check is sufficient, no file locks.
- Timeout enforcement is centralized: one watchdog thread, deterministic cleanup.
- Simpler than distributed coordination (file locks, PID validation, stale cleanup).

## Module Layout

```
phone_cli/
├── daemon/
│   ├── server.py        # Daemon main loop, Unix socket server, lifecycle
│   ├── session.py       # SessionManager: session create/activate/expire/release
│   ├── device.py        # DeviceManager: connect/disconnect/execute, port allocation
│   ├── watchdog.py      # TimeoutWatchdog: idle session expiry
│   └── protocol.py      # IPC request/response schema, command dispatch
├── client.py            # PhoneClient: lightweight client for AI sessions
├── config/
│   └── ports.py         # Port range constants, bind-check utility
├── adb/connection.py    # Unchanged, called by DeviceManager internally
├── hdc/connection.py    # Unchanged, called by DeviceManager internally
└── ios/connection.py    # Unchanged, called by DeviceManager internally
```

## Port Allocation

### Ranges

| Platform    | Purpose       | Default | Dynamic Range |
|-------------|---------------|---------|---------------|
| iOS WDA     | wdaproxy      | 8100    | 8100-8199     |
| ADB Server  | adb -P        | 5037    | 5037-5099     |
| HDC Server  | hdc server    | 5100    | 5100-5199     |

### Allocation Algorithm

Runs inside the daemon process (single-threaded allocation, no race conditions):

```
for port in range(start, end):
    1. bind-check: socket.bind(('127.0.0.1', port))
       - Fails → port occupied by external process → skip
    2. Check internal registry: port already assigned to another device?
       - Yes → skip
    3. Assign port, record in registry → return port

If all ports exhausted → raise PortExhaustedError
```

Default port is tried first for backward compatibility (single-session gets 8100/5037).

### Bind Check Implementation

```python
def is_port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(('127.0.0.1', port))
            return True
        except OSError:
            return False
```

bind-check catches all occupied states including TIME_WAIT, unlike connect-check which only detects listening ports.

## Session Lifecycle

### States

```
acquire() called
    │
    ├── device free ──▶ ACTIVE
    │
    └── device busy ──▶ QUEUED ──(prev session released)──▶ ACTIVE
                                                               │
                                             ┌─────────────────┤
                                             ▼                 ▼
                                         RELEASED          EXPIRED
                                      (AI calls release)  (timeout)
```

### Session Data

```python
@dataclass
class Session:
    session_id: str         # UUID
    device_id: str          # Target device identifier
    device_type: str        # "ios" | "adb" | "hdc"
    status: str             # "active" | "queued" | "released" | "expired"
    acquired_at: float      # Time when session became active
    last_active_at: float   # Updated on every operate/heartbeat
    timeout: float          # Idle timeout in seconds (default 300)
    created_at: float       # Time when acquire was called
```

### Timeout

- Default: 300 seconds (5 minutes) of no operate/heartbeat calls.
- Configurable per-session via `acquire(timeout=N)`.
- Watchdog thread checks every 10 seconds.
- On expiry: session marked expired, device disconnected, port released, next queued session activated.

## IPC Protocol

Communication over Unix socket `~/.phone-cli/phone-cli.sock`, JSON newline-delimited.

### Commands

#### acquire

Request a device connection.

```json
{
  "cmd": "acquire",
  "args": {
    "device_id": "emulator-5554",
    "device_type": "adb",
    "timeout": 300
  }
}
```

Response (success, device available):
```json
{
  "ok": true,
  "session_id": "uuid-xxx",
  "status": "active",
  "port": 5037,
  "device_id": "emulator-5554"
}
```

Response (device busy, queued):
```json
{
  "ok": true,
  "session_id": "uuid-yyy",
  "status": "queued",
  "queue_position": 1
}
```

#### operate

Execute a device action. Resets the idle timeout timer.

```json
{
  "cmd": "operate",
  "args": {
    "session_id": "uuid-xxx",
    "action": "tap",
    "x": 100,
    "y": 200
  }
}
```

Response:
```json
{"ok": true, "result": {}}
```

Error (session expired):
```json
{"ok": false, "error": "session_expired", "msg": "Session timed out after 300s idle"}
```

#### release

Voluntarily release a device.

```json
{"cmd": "release", "args": {"session_id": "uuid-xxx"}}
```

#### heartbeat

Keep session alive without performing an operation.

```json
{"cmd": "heartbeat", "args": {"session_id": "uuid-xxx"}}
```

#### status

Query daemon state.

```json
{"cmd": "status", "args": {}}
```

Response:
```json
{
  "ok": true,
  "sessions": [
    {"session_id": "uuid-xxx", "device_id": "emulator-5554", "status": "active", "idle_seconds": 42}
  ],
  "devices": [
    {"device_id": "emulator-5554", "device_type": "adb", "port": 5037, "status": "occupied"}
  ]
}
```

#### list_devices

Discover available devices.

```json
{"cmd": "list_devices", "args": {"device_type": "ios"}}
```

## Device Manager

### Per-Platform Connection Strategy

**iOS:**
- Allocate WDA port from 8100-8199.
- Start `tidevice -u <udid> wdaproxy --port <allocated_port>` as subprocess.
- Create `wda.Client(f"http://localhost:{allocated_port}")`.
- On disconnect: terminate wdaproxy subprocess, release port.

**ADB:**
- Allocate ADB server port from 5037-5099.
- Start isolated ADB server: `adb -P <allocated_port> start-server`.
- All device commands go through: `adb -P <allocated_port> -s <device_id> ...`.
- On disconnect: `adb -P <allocated_port> kill-server`, release port.

**HDC:**
- Allocate HDC server port from 5100-5199.
- Start isolated HDC server on allocated port.
- All device commands go through the allocated server.
- On disconnect: kill server, release port.

### DeviceSlot

```python
@dataclass
class DeviceSlot:
    device_id: str
    device_type: str              # "ios" | "adb" | "hdc"
    port: int                     # Allocated port
    current_session_id: str | None
    process: subprocess.Popen | None  # wdaproxy / adb server subprocess
    connected_at: float
```

## Client API

```python
class PhoneClient:
    """Lightweight client for AI sessions to communicate with daemon."""

    def __init__(self, socket_path="~/.phone-cli/phone-cli.sock"):
        self._socket_path = os.path.expanduser(socket_path)
        self._session_id: str | None = None

    def acquire(self, device_id: str, device_type: str = "auto",
                timeout: float = 300) -> dict:
        """Acquire a device. Stores session_id internally."""

    def tap(self, x: int, y: int) -> dict:
        """Tap at coordinates."""

    def swipe(self, x1, y1, x2, y2, duration=300) -> dict:
        """Swipe gesture."""

    def screenshot(self, path: str | None = None) -> dict:
        """Take screenshot."""

    def release(self) -> None:
        """Release device, clear session."""

    def heartbeat(self) -> None:
        """Keep-alive without operation."""
```

All `tap`/`swipe`/`screenshot`/etc. methods call `_operate(action, **args)` internally, which sends the operate command and auto-refreshes the timeout.

## Migration from Existing Architecture

### What Changes

| Before | After |
|--------|-------|
| Per-device-type daemon instances (adb/hdc/ios) | Single global daemon |
| `~/.phone-cli/instances/{adb,hdc,ios}/` | `~/.phone-cli/` (single home) |
| Multiple pid/socket/state files | One pid, one socket, one state |
| Device operations in CLI process | Device operations in daemon process |
| No session concept | Explicit acquire/operate/release |
| No timeout | Configurable idle timeout (default 300s) |
| Hardcoded ports | Dynamic port allocation |

### What Stays

- `phone_cli/adb/connection.py` — ADBConnection class, used by DeviceManager.
- `phone_cli/hdc/connection.py` — HDCConnection class, used by DeviceManager.
- `phone_cli/ios/connection.py` — WDAConnection class, used by DeviceManager.
- CLI commands (`phone-cli start/stop/status`) — updated to talk to new daemon.
- Unix socket IPC pattern — same mechanism, enhanced protocol.

### Backward Compatibility

- Single AI session: acquires device, gets default port (8100/5037), behavior identical to before.
- Existing CLI commands continue to work.
- `phone-cli start --device-type ios` starts the global daemon and auto-acquires the specified device type.

## Testing Strategy

- Unit tests for SessionManager: acquire/release/expire state transitions, queue ordering.
- Unit tests for port allocation: range scanning, bind-check mocking, exhaustion.
- Unit tests for TimeoutWatchdog: expiry detection, queue activation.
- Integration tests for IPC: client-daemon round-trip via real Unix socket.
- E2E tests (with devices): full acquire-operate-release cycle.
