"""Discovery helpers for selecting an iOS automation runtime."""

from __future__ import annotations

import json
import platform
import subprocess
from dataclasses import dataclass, field
from typing import Any, Literal

IOSRuntime = Literal["device", "simulator", "app_on_mac"]
SelectionMode = Literal["auto_selected", "selection_required", "unavailable"]
ProviderResult = tuple[list["RuntimeCandidate"], list["DiscoveryReason"]]


@dataclass(frozen=True)
class RuntimeCandidate:
    """A single runtime target that is currently available for use."""

    runtime: IOSRuntime
    target_id: str
    label: str
    status: str = "available"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime": self.runtime,
            "target_id": self.target_id,
            "label": self.label,
            "status": self.status,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class DiscoveryReason:
    """Explains why a runtime is not available or could not be validated."""

    runtime: IOSRuntime
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime": self.runtime,
            "code": self.code,
            "message": self.message,
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class RuntimeDiscoveryResult:
    """Combined discovery result consumed by CLI and higher-level skills."""

    candidates: list[RuntimeCandidate]
    reasons: list[DiscoveryReason]

    @property
    def auto_selectable(self) -> bool:
        return len(self.candidates) == 1

    @property
    def selection_required(self) -> bool:
        return len(self.candidates) > 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "auto_selectable": self.auto_selectable,
            "selection_required": self.selection_required,
            "reasons": [reason.to_dict() for reason in self.reasons],
        }


@dataclass(frozen=True)
class RuntimeSelectionOutcome:
    """Resolved selection outcome for the current discovery result."""

    mode: SelectionMode
    candidate: RuntimeCandidate | None = None
    error_code: str | None = None
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = {
            "mode": self.mode,
            "candidate": self.candidate.to_dict() if self.candidate else None,
            "error_code": self.error_code,
            "message": self.message,
        }
        return data


def detect_ios_runtimes() -> RuntimeDiscoveryResult:
    """Discover all currently usable iOS runtime candidates."""

    candidates: list[RuntimeCandidate] = []
    reasons: list[DiscoveryReason] = []

    for provider in (
        detect_device_candidates,
        detect_simulator_candidates,
        detect_app_on_mac_candidates,
    ):
        provider_candidates, provider_reasons = provider()
        candidates.extend(provider_candidates)
        reasons.extend(provider_reasons)

    return RuntimeDiscoveryResult(candidates=candidates, reasons=reasons)


def resolve_runtime_selection(
    result: RuntimeDiscoveryResult,
) -> RuntimeSelectionOutcome:
    """Apply the agreed P0 selection rules to a discovery result."""

    if not result.candidates:
        return RuntimeSelectionOutcome(
            mode="unavailable",
            error_code="NO_AVAILABLE_IOS_RUNTIME",
            message="No available iOS runtime candidates were detected.",
        )

    if len(result.candidates) == 1:
        candidate = result.candidates[0]
        return RuntimeSelectionOutcome(
            mode="auto_selected",
            candidate=candidate,
            message=f"Auto-selected the only available runtime: {candidate.label}.",
        )

    return RuntimeSelectionOutcome(
        mode="selection_required",
        error_code="RUNTIME_SELECTION_REQUIRED",
        message="Multiple iOS runtime candidates were detected; explicit selection is required.",
    )


def detect_device_candidates() -> ProviderResult:
    """Discover USB-connected iOS devices via tidevice."""

    runtime: IOSRuntime = "device"

    try:
        result = subprocess.run(
            ["tidevice", "list", "--json"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except FileNotFoundError:
        return [], [
            DiscoveryReason(
                runtime=runtime,
                code="tidevice_unavailable",
                message="tidevice is not installed or not on PATH.",
            )
        ]
    except Exception as exc:
        return [], [
            DiscoveryReason(
                runtime=runtime,
                code="device_provider_failed",
                message=f"Failed to run tidevice: {exc}",
            )
        ]

    if result.returncode != 0:
        stderr = (result.stderr or result.stdout or "").strip()
        return [], [
            DiscoveryReason(
                runtime=runtime,
                code="device_provider_failed",
                message="tidevice list failed.",
                details={"stderr": stderr},
            )
        ]

    try:
        device_rows = json.loads(result.stdout or "[]")
    except json.JSONDecodeError as exc:
        return [], [
            DiscoveryReason(
                runtime=runtime,
                code="device_provider_invalid_json",
                message=f"tidevice returned invalid JSON: {exc}",
            )
        ]

    if not device_rows:
        return [], [
            DiscoveryReason(
                runtime=runtime,
                code="no_connected_devices",
                message="No USB-connected iOS devices were detected.",
            )
        ]

    candidates = []
    for row in device_rows:
        udid = row.get("udid")
        if not udid:
            continue
        name = row.get("name") or row.get("model") or udid
        candidates.append(
            RuntimeCandidate(
                runtime=runtime,
                target_id=udid,
                label=name,
                metadata={
                    "source": "tidevice",
                    "device_name": row.get("name"),
                    "model": row.get("model"),
                },
            )
        )

    if candidates:
        return candidates, []

    return [], [
        DiscoveryReason(
            runtime=runtime,
            code="device_provider_empty",
            message="tidevice returned rows, but none contained a usable UDID.",
        )
    ]


def detect_simulator_candidates() -> ProviderResult:
    """Discover booted iOS Simulator targets via simctl."""

    runtime: IOSRuntime = "simulator"

    try:
        result = subprocess.run(
            ["xcrun", "simctl", "list", "--json", "devices"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except FileNotFoundError:
        return [], [
            DiscoveryReason(
                runtime=runtime,
                code="simctl_unavailable",
                message="xcrun simctl is not available on PATH.",
            )
        ]
    except Exception as exc:
        return [], [
            DiscoveryReason(
                runtime=runtime,
                code="simulator_provider_failed",
                message=f"Failed to run simctl: {exc}",
            )
        ]

    if result.returncode != 0:
        stderr = (result.stderr or result.stdout or "").strip()
        return [], [
            DiscoveryReason(
                runtime=runtime,
                code="simulator_provider_failed",
                message="simctl list failed.",
                details={"stderr": stderr},
            )
        ]

    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        return [], [
            DiscoveryReason(
                runtime=runtime,
                code="simulator_provider_invalid_json",
                message=f"simctl returned invalid JSON: {exc}",
            )
        ]

    booted: list[RuntimeCandidate] = []
    for runtime_name, rows in payload.get("devices", {}).items():
        for row in rows:
            if row.get("state") != "Booted":
                continue
            if row.get("isAvailable") is False:
                continue
            udid = row.get("udid")
            if not udid:
                continue
            name = row.get("name") or udid
            booted.append(
                RuntimeCandidate(
                    runtime=runtime,
                    target_id=udid,
                    label=f"{name} (Booted)",
                    metadata={
                        "source": "simctl",
                        "runtime_version": runtime_name,
                        "state": row.get("state"),
                        "is_available": row.get("isAvailable"),
                    },
                )
            )

    if booted:
        return booted, []

    return [], [
        DiscoveryReason(
            runtime=runtime,
            code="no_booted_simulators",
            message="No booted iOS Simulator targets were detected.",
        )
    ]


def detect_app_on_mac_candidates() -> ProviderResult:
    """Discover whether the local Apple Silicon host can automate app_on_mac."""

    runtime: IOSRuntime = "app_on_mac"

    from phone_cli.ios.host.permissions import check_app_on_mac_host_support

    support = check_app_on_mac_host_support()
    if not support.supported:
        reasons = [
            DiscoveryReason(
                runtime=runtime,
                code=reason.code,
                message=reason.message,
                details=dict(reason.details),
            )
            for reason in support.reasons
        ]
        return [], reasons

    return [
        RuntimeCandidate(
            runtime=runtime,
            target_id="local-mac",
            label="Local Apple Silicon Mac",
            metadata={
                "source": "host",
                "platform": platform.system(),
                "machine": platform.machine(),
                "dependencies": dict(support.dependencies),
            },
        )
    ], []
