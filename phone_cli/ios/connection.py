"""iOS device connection management via tidevice + WDA."""

import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Optional

try:
    import tidevice
    import wda

    _HAS_IOS_DEPS = True
except ImportError:
    _HAS_IOS_DEPS = False


def _check_deps() -> None:
    """Raise ImportError with install hint if iOS dependencies are missing."""
    if not _HAS_IOS_DEPS:
        raise ImportError(
            "iOS dependencies not installed. Run: pip install phone-cli[ios]"
        )


@dataclass
class DeviceInfo:
    """Information about a connected iOS device."""

    device_id: str
    status: str
    model: str | None = None
    ios_version: str | None = None


class WDAConnection:
    """
    Manages WDA connections to iOS devices via tidevice.

    Uses tidevice to discover USB-connected devices and start wdaproxy,
    then provides a cached wda.Client for device control.
    """

    _instances: dict[str, "WDAConnection"] = {}
    _lock = threading.Lock()

    def __init__(self, device_id: str | None = None):
        _check_deps()
        self.device_id = device_id
        self._client: Optional["wda.Client"] = None
        self._proxy_proc: Optional[subprocess.Popen] = None
        self._wda_port = 8100

    @classmethod
    def get_instance(cls, device_id: str | None = None) -> "WDAConnection":
        """Get or create a cached WDAConnection for the given device."""
        key = device_id or "__default__"
        with cls._lock:
            if key not in cls._instances:
                cls._instances[key] = cls(device_id)
            return cls._instances[key]

    def connect(self) -> "wda.Client":
        """Connect to device via WDA, starting wdaproxy if needed."""
        _check_deps()

        if self._client is not None:
            try:
                self._client.status()
                return self._client
            except Exception:
                self._client = None

        # Start wdaproxy via tidevice
        self._start_wdaproxy()

        # Connect wda client
        self._client = wda.Client(f"http://localhost:{self._wda_port}")

        # Wait for WDA to become ready
        for _ in range(30):
            try:
                self._client.status()
                return self._client
            except Exception:
                time.sleep(1)

        raise ConnectionError("WDA did not become ready within 30 seconds")

    def _start_wdaproxy(self) -> None:
        """Start tidevice wdaproxy subprocess if not already running."""
        if self._proxy_proc is not None and self._proxy_proc.poll() is None:
            return

        cmd = ["tidevice"]
        if self.device_id:
            cmd.extend(["-u", self.device_id])
        cmd.extend(["wdaproxy", "-B", "com.facebook.WebDriverAgentRunner.xctrunner",
                     "--port", str(self._wda_port)])

        self._proxy_proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        # Give wdaproxy a moment to start
        time.sleep(3)

    def disconnect(self) -> None:
        """Stop the wdaproxy subprocess and clean up."""
        if self._proxy_proc is not None:
            self._proxy_proc.terminate()
            try:
                self._proxy_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proxy_proc.kill()
            self._proxy_proc = None
        self._client = None

        key = self.device_id or "__default__"
        with self._lock:
            self._instances.pop(key, None)

    def list_devices(self) -> list[DeviceInfo]:
        """List connected iOS devices via tidevice."""
        return list_devices()


def get_wda_client(device_id: str | None = None) -> "wda.Client":
    """
    Get a WDA client for the given device, auto-connecting if needed.

    This is the primary entry point used by device/input/screenshot modules.

    Args:
        device_id: Optional iOS device UDID.

    Returns:
        A connected wda.Client instance.
    """
    conn = WDAConnection.get_instance(device_id)
    return conn.connect()


def list_devices() -> list[DeviceInfo]:
    """
    List connected iOS devices via tidevice.

    Returns:
        List of DeviceInfo objects.
    """
    _check_deps()

    try:
        result = subprocess.run(
            ["tidevice", "list", "--json"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            return []

        import json
        devices_data = json.loads(result.stdout) if result.stdout.strip() else []

        devices = []
        for d in devices_data:
            devices.append(
                DeviceInfo(
                    device_id=d.get("udid", ""),
                    status="device",
                    model=d.get("name", None),
                )
            )
        return devices

    except FileNotFoundError:
        # tidevice not installed
        return []
    except Exception:
        return []


def quick_connect(device_id: str | None = None) -> tuple[bool, str]:
    """
    Quick helper to connect to an iOS device.

    Args:
        device_id: Optional device UDID.

    Returns:
        Tuple of (success, message).
    """
    try:
        conn = WDAConnection.get_instance(device_id)
        conn.connect()
        return True, f"Connected to iOS device {device_id or '(default)'}"
    except Exception as e:
        return False, f"Connection error: {e}"
