"""Host dependency and permission checks for macOS-backed iOS runtimes."""

from __future__ import annotations

import importlib
import platform
from dataclasses import dataclass, field
from typing import Any, Literal

PermissionState = Literal[
    "granted",
    "denied",
    "missing_dependency",
    "unknown",
    "not_applicable",
]

REQUIRED_APP_ON_MAC_MODULES = (
    "AppKit",
    "Quartz",
    "ApplicationServices",
)
REQUIRED_SIMULATOR_MODULES = (
    "AppKit",
    "Quartz",
    "ApplicationServices",
)


@dataclass(frozen=True)
class HostSupportReason:
    """A structured reason explaining why host automation is unavailable."""

    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class PermissionStatus:
    """Represents one host-level permission check."""

    name: str
    state: PermissionState
    detail: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "name": self.name,
            "state": self.state,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class HostAutomationSupport:
    """Summarizes whether the current host can support app_on_mac automation."""

    supported: bool
    platform: str
    machine: str
    dependencies: dict[str, str]
    accessibility: PermissionStatus
    screen_recording: PermissionStatus
    reasons: list[HostSupportReason]

    def to_dict(self) -> dict[str, Any]:
        return {
            "supported": self.supported,
            "platform": self.platform,
            "machine": self.machine,
            "dependencies": dict(self.dependencies),
            "accessibility": self.accessibility.to_dict(),
            "screen_recording": self.screen_recording.to_dict(),
            "reasons": [reason.to_dict() for reason in self.reasons],
        }


def get_host_dependency_status() -> dict[str, str]:
    """Return import status for the modules required by app_on_mac support."""

    statuses: dict[str, str] = {}
    for module_name in REQUIRED_APP_ON_MAC_MODULES:
        try:
            importlib.import_module(module_name)
            statuses[module_name] = "ok"
        except Exception as exc:
            statuses[module_name] = f"missing: {exc}"
    return statuses


def check_accessibility_permission() -> PermissionStatus:
    """Check macOS Accessibility permission without prompting the user."""

    if platform.system() != "Darwin":
        return PermissionStatus(
            name="accessibility",
            state="not_applicable",
            detail="Accessibility checks only apply on macOS.",
        )

    try:
        from ApplicationServices import AXIsProcessTrusted
    except Exception as exc:
        return PermissionStatus(
            name="accessibility",
            state="missing_dependency",
            detail=str(exc),
        )

    try:
        trusted = bool(AXIsProcessTrusted())
    except Exception as exc:
        return PermissionStatus(
            name="accessibility",
            state="unknown",
            detail=str(exc),
        )

    return PermissionStatus(
        name="accessibility",
        state="granted" if trusted else "denied",
        detail=None if trusted else "Accessibility permission is not granted.",
    )


def check_screen_recording_permission() -> PermissionStatus:
    """Check macOS Screen Recording permission without prompting the user."""

    if platform.system() != "Darwin":
        return PermissionStatus(
            name="screen_recording",
            state="not_applicable",
            detail="Screen Recording checks only apply on macOS.",
        )

    try:
        import Quartz
    except Exception as exc:
        return PermissionStatus(
            name="screen_recording",
            state="missing_dependency",
            detail=str(exc),
        )

    preflight = getattr(Quartz, "CGPreflightScreenCaptureAccess", None)
    if preflight is None:
        return PermissionStatus(
            name="screen_recording",
            state="unknown",
            detail="Quartz does not expose CGPreflightScreenCaptureAccess.",
        )

    try:
        granted = bool(preflight())
    except Exception as exc:
        return PermissionStatus(
            name="screen_recording",
            state="unknown",
            detail=str(exc),
        )

    return PermissionStatus(
        name="screen_recording",
        state="granted" if granted else "denied",
        detail=None if granted else "Screen Recording permission is not granted.",
    )


def check_app_on_mac_host_support() -> HostAutomationSupport:
    """Return whether the current host is usable for app_on_mac automation."""

    platform_name = platform.system()
    machine = platform.machine()
    dependencies = get_host_dependency_status()
    accessibility = check_accessibility_permission()
    screen_recording = check_screen_recording_permission()

    reasons: list[HostSupportReason] = []

    if platform_name != "Darwin":
        reasons.append(
            HostSupportReason(
                code="host_not_macos",
                message="app_on_mac requires macOS.",
                details={"platform": platform_name},
            )
        )

    if machine not in {"arm64", "aarch64"}:
        reasons.append(
            HostSupportReason(
                code="host_not_apple_silicon",
                message="app_on_mac requires an Apple Silicon Mac.",
                details={"machine": machine},
            )
        )

    missing_modules = [
        module_name
        for module_name, status in dependencies.items()
        if status != "ok"
    ]
    if missing_modules:
        reasons.append(
            HostSupportReason(
                code="host_dependencies_missing",
                message="Required macOS automation dependencies are missing.",
                details={"missing_modules": missing_modules},
            )
        )

    if accessibility.state != "granted":
        reasons.append(
            HostSupportReason(
                code="accessibility_permission_required",
                message="Accessibility permission is required for host automation.",
                details={"state": accessibility.state, "detail": accessibility.detail},
            )
        )

    if screen_recording.state != "granted":
        reasons.append(
            HostSupportReason(
                code="screen_recording_permission_required",
                message="Screen Recording permission is required for host automation.",
                details={
                    "state": screen_recording.state,
                    "detail": screen_recording.detail,
                },
            )
        )

    return HostAutomationSupport(
        supported=not reasons,
        platform=platform_name,
        machine=machine,
        dependencies=dependencies,
        accessibility=accessibility,
        screen_recording=screen_recording,
        reasons=reasons,
    )


def check_simulator_host_support() -> HostAutomationSupport:
    """Return whether the current host can drive Simulator UI via host events."""

    platform_name = platform.system()
    machine = platform.machine()
    all_dependencies = get_host_dependency_status()
    dependencies = {
        module_name: all_dependencies.get(module_name, "missing")
        for module_name in REQUIRED_SIMULATOR_MODULES
    }
    accessibility = check_accessibility_permission()
    screen_recording = PermissionStatus(
        name="screen_recording",
        state="not_applicable",
        detail="Simulator MVP uses simctl screenshots instead of host screen capture.",
    )

    reasons: list[HostSupportReason] = []

    if platform_name != "Darwin":
        reasons.append(
            HostSupportReason(
                code="host_not_macos",
                message="Simulator host automation requires macOS.",
                details={"platform": platform_name},
            )
        )

    missing_modules = [
        module_name
        for module_name, status in dependencies.items()
        if status != "ok"
    ]
    if missing_modules:
        reasons.append(
            HostSupportReason(
                code="host_dependencies_missing",
                message="Required Simulator host automation dependencies are missing.",
                details={"missing_modules": missing_modules},
            )
        )

    if accessibility.state != "granted":
        reasons.append(
            HostSupportReason(
                code="accessibility_permission_required",
                message="Accessibility permission is required for Simulator event injection.",
                details={"state": accessibility.state, "detail": accessibility.detail},
            )
        )

    return HostAutomationSupport(
        supported=not reasons,
        platform=platform_name,
        machine=machine,
        dependencies=dependencies,
        accessibility=accessibility,
        screen_recording=screen_recording,
        reasons=reasons,
    )
