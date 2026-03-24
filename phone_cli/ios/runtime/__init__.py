"""Runtime primitives for multi-runtime iOS support."""

from phone_cli.ios.runtime.base import (
    IOSBackend,
    IOSCapabilities,
    IOSTargetInfo,
    UnsupportedOperationError,
)
from phone_cli.ios.runtime.discovery import (
    DiscoveryReason,
    RuntimeCandidate,
    RuntimeDiscoveryResult,
    RuntimeSelectionOutcome,
    detect_ios_runtimes,
    resolve_runtime_selection,
)
from phone_cli.ios.runtime.router import get_backend, normalize_runtime, resolve_runtime

__all__ = [
    "DiscoveryReason",
    "IOSBackend",
    "IOSCapabilities",
    "IOSTargetInfo",
    "RuntimeCandidate",
    "RuntimeDiscoveryResult",
    "RuntimeSelectionOutcome",
    "UnsupportedOperationError",
    "detect_ios_runtimes",
    "get_backend",
    "normalize_runtime",
    "resolve_runtime_selection",
    "resolve_runtime",
]
