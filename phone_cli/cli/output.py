"""Unified JSON output format for phone-cli commands."""

import json
from typing import Any


class ErrorCode:
    """Error codes for CLI responses."""
    DEVICE_DISCONNECTED = "DEVICE_DISCONNECTED"
    DEVICE_LOCKED = "DEVICE_LOCKED"
    APP_NOT_FOUND = "APP_NOT_FOUND"
    SCREENSHOT_FAILED = "SCREENSHOT_FAILED"
    COMMAND_TIMEOUT = "COMMAND_TIMEOUT"
    DAEMON_NOT_RUNNING = "DAEMON_NOT_RUNNING"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    QUEUE_FULL = "QUEUE_FULL"
    UI_TREE_UNAVAILABLE = "UI_TREE_UNAVAILABLE"
    APP_NOT_RUNNING = "APP_NOT_RUNNING"
    INSTALL_FAILED = "INSTALL_FAILED"
    SCREEN_CHECK_FAILED = "SCREEN_CHECK_FAILED"
    UNSUPPORTED_OPERATION = "UNSUPPORTED_OPERATION"
    TARGET_NOT_SELECTED = "TARGET_NOT_SELECTED"
    INSTANCE_SELECTION_REQUIRED = "INSTANCE_SELECTION_REQUIRED"
    NO_AVAILABLE_IOS_RUNTIME = "NO_AVAILABLE_IOS_RUNTIME"
    RUNTIME_SELECTION_REQUIRED = "RUNTIME_SELECTION_REQUIRED"
    RUNTIME_NOT_SUPPORTED = "RUNTIME_NOT_SUPPORTED"
    UNKNOWN_COMMAND = "UNKNOWN_COMMAND"
    COMMAND_FAILED = "COMMAND_FAILED"
    COMPANION_UNAVAILABLE = "COMPANION_UNAVAILABLE"
    COMPANION_BUILD_FAILED = "COMPANION_BUILD_FAILED"


def ok_response(data: dict[str, Any] | None = None) -> str:
    """Format a success response as JSON string."""
    return json.dumps({"status": "ok", "data": data}, ensure_ascii=False)


def error_response(error_code: str, error_msg: str) -> str:
    """Format an error response as JSON string."""
    return json.dumps(
        {"status": "error", "error_code": error_code, "error_msg": error_msg},
        ensure_ascii=False,
    )
