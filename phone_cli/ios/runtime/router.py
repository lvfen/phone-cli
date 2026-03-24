"""Runtime router for selecting the correct iOS backend."""

from __future__ import annotations

from typing import Any

from phone_cli.ios.runtime.app_on_mac_backend import AppOnMacBackend
from phone_cli.ios.runtime.base import IOSBackend
from phone_cli.ios.runtime.device_backend import DeviceBackend
from phone_cli.ios.runtime.discovery import IOSRuntime
from phone_cli.ios.runtime.simulator_backend import SimulatorBackend

_BACKENDS: dict[IOSRuntime, IOSBackend] = {
    "device": DeviceBackend(),
    "simulator": SimulatorBackend(),
    "app_on_mac": AppOnMacBackend(),
}


def normalize_runtime(runtime: str | None) -> IOSRuntime:
    """Normalize CLI/runtime strings to the canonical internal enum."""

    normalized = (runtime or "device").replace("-", "_")
    if normalized not in _BACKENDS:
        raise ValueError(f"Unsupported iOS runtime: {runtime}")
    return normalized  # type: ignore[return-value]


def resolve_runtime(
    runtime: str | None = None,
    state: dict[str, Any] | None = None,
) -> IOSRuntime:
    """Resolve an explicit runtime override or fall back to daemon state/default."""

    if runtime:
        return normalize_runtime(runtime)
    if state and state.get("ios_runtime"):
        return normalize_runtime(str(state["ios_runtime"]))
    return "device"


def get_backend(
    runtime: str | None = None,
    state: dict[str, Any] | None = None,
) -> IOSBackend:
    """Return the backend selected by explicit runtime or daemon state."""

    resolved_runtime = resolve_runtime(runtime=runtime, state=state)
    return _BACKENDS[resolved_runtime]
