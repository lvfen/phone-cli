"""CLI command handlers for phone-cli daemon."""

import base64
import json
import os
import subprocess
import time
import uuid
import xml.etree.ElementTree as ET
from typing import Any

from phone_cli.cli.output import ErrorCode, error_response, ok_response


class CoordConverter:
    """Converts 0-999 relative coordinates to absolute pixel coordinates."""

    def __init__(self, screen_width: int, screen_height: int):
        self.screen_width = screen_width
        self.screen_height = screen_height

    def to_absolute(self, rx: int, ry: int) -> tuple[int, int]:
        """Convert relative coords (0-999) to absolute pixels."""
        rx = max(0, min(999, rx))
        ry = max(0, min(999, ry))
        x = int(rx / 999 * self.screen_width)
        y = int(ry / 999 * self.screen_height)
        return min(x, self.screen_width - 1), min(y, self.screen_height - 1)


# ── Command registry ──────────────────────────────────────────────────

_COMMANDS: dict[str, Any] = {}


def _register(name: str):
    """Decorator to register a command handler."""
    def decorator(fn):
        _COMMANDS[name] = fn
        return fn
    return decorator


def dispatch_command(cmd: str, args: dict, daemon: Any) -> str:
    """Route a command string to the appropriate handler."""
    handler = _COMMANDS.get(cmd)
    if handler is None:
        return error_response(ErrorCode.UNKNOWN_COMMAND, f"Unknown command: {cmd}")
    try:
        return handler(args, daemon)
    except Exception as e:
        return error_response(ErrorCode.COMMAND_FAILED, str(e))


# ── Helpers ───────────────────────────────────────────────────────────

def _get_device_module(daemon: Any):
    """Return the adb, hdc, or ios module based on daemon state."""
    state = daemon._read_state()
    device_type = state.get("device_type", "adb")
    if device_type == "hdc":
        from phone_cli import hdc
        return hdc
    elif device_type == "ios":
        from phone_cli import ios
        return ios
    else:
        from phone_cli import adb
        return adb


def _get_device_id(args: dict, daemon: Any) -> str | None:
    """Get device_id from args or daemon state."""
    device_id = args.get("device_id")
    if device_id:
        return device_id
    state = daemon._read_state()
    return state.get("device_id")


def _get_screen_size(daemon: Any) -> tuple[int, int]:
    """Get screen size from daemon state, default [1080, 2400]."""
    state = daemon._read_state()
    size = state.get("screen_size", [1080, 2400])
    return size[0], size[1]


def _get_device_type(daemon: Any) -> str:
    """Get device_type from daemon state."""
    state = daemon._read_state()
    return state.get("device_type", "adb")


# ── Command handlers ─────────────────────────────────────────────────

@_register("status")
def _cmd_status(args: dict, daemon: Any) -> str:
    return ok_response(daemon.status())


@_register("devices")
def _cmd_devices(args: dict, daemon: Any) -> str:
    device_type = _get_device_type(daemon)
    if device_type == "hdc":
        from phone_cli import hdc
        devices = hdc.list_devices()
    elif device_type == "ios":
        from phone_cli import ios
        devices = ios.list_devices()
    else:
        from phone_cli import adb
        devices = adb.list_devices()
    device_list = [
        {
            "device_id": d.device_id,
            "model": getattr(d, "model", ""),
            "status": getattr(d, "status", ""),
        }
        for d in devices
    ]
    return ok_response({"devices": device_list})


@_register("set_device")
def _cmd_set_device(args: dict, daemon: Any) -> str:
    device_id = args.get("device_id")
    state = daemon._read_state()
    state["device_id"] = device_id
    daemon._write_state(state)
    return ok_response({"device_id": device_id})


@_register("device_info")
def _cmd_device_info(args: dict, daemon: Any) -> str:
    state = daemon._read_state()
    return ok_response({
        "device_type": state.get("device_type"),
        "device_id": state.get("device_id"),
        "screen_size": state.get("screen_size"),
        "device_status": state.get("device_status"),
    })


@_register("screenshot")
def _cmd_screenshot(args: dict, daemon: Any) -> str:
    device_id = _get_device_id(args, daemon)
    device_mod = _get_device_module(daemon)
    try:
        screenshot = device_mod.get_screenshot(device_id=device_id)
    except Exception as e:
        return error_response(ErrorCode.SCREENSHOT_FAILED, str(e))

    # Determine filename
    step = args.get("step")
    if step is not None:
        filename = f"step_{step}.png"
    else:
        filename = f"{uuid.uuid4()}.png"

    os.makedirs(daemon.screenshot_dir, exist_ok=True)
    file_path = os.path.join(daemon.screenshot_dir, filename)

    # Decode and optionally resize, then save
    try:
        img_data = base64.b64decode(screenshot.base64_data)
        resize = args.get("resize")
        if resize:
            from PIL import Image
            from io import BytesIO
            img = Image.open(BytesIO(img_data))
            ratio = int(resize) / img.width
            new_size = (int(resize), int(img.height * ratio))
            img = img.resize(new_size, Image.LANCZOS)
            buf = BytesIO()
            img.save(buf, format="PNG")
            img_data = buf.getvalue()
            final_width, final_height = new_size
        else:
            from PIL import Image
            from io import BytesIO
            img = Image.open(BytesIO(img_data))
            final_width, final_height = img.width, img.height

        with open(file_path, "wb") as f:
            f.write(img_data)
    except Exception as e:
        return error_response(ErrorCode.SCREENSHOT_FAILED, str(e))

    return ok_response({
        "path": file_path,
        "width": final_width,
        "height": final_height,
    })


@_register("tap")
def _cmd_tap(args: dict, daemon: Any) -> str:
    device_id = _get_device_id(args, daemon)
    w, h = _get_screen_size(daemon)
    conv = CoordConverter(w, h)
    x, y = conv.to_absolute(args["x"], args["y"])
    device_mod = _get_device_module(daemon)
    device_mod.tap(x, y, device_id=device_id)
    return ok_response({"x": x, "y": y})


@_register("double_tap")
def _cmd_double_tap(args: dict, daemon: Any) -> str:
    device_id = _get_device_id(args, daemon)
    w, h = _get_screen_size(daemon)
    conv = CoordConverter(w, h)
    x, y = conv.to_absolute(args["x"], args["y"])
    device_mod = _get_device_module(daemon)
    device_mod.double_tap(x, y, device_id=device_id)
    return ok_response({"x": x, "y": y})


@_register("long_press")
def _cmd_long_press(args: dict, daemon: Any) -> str:
    device_id = _get_device_id(args, daemon)
    w, h = _get_screen_size(daemon)
    conv = CoordConverter(w, h)
    x, y = conv.to_absolute(args["x"], args["y"])
    device_mod = _get_device_module(daemon)
    device_mod.long_press(x, y, device_id=device_id)
    return ok_response({"x": x, "y": y})


@_register("swipe")
def _cmd_swipe(args: dict, daemon: Any) -> str:
    device_id = _get_device_id(args, daemon)
    w, h = _get_screen_size(daemon)
    conv = CoordConverter(w, h)
    sx, sy = conv.to_absolute(args["start_x"], args["start_y"])
    ex, ey = conv.to_absolute(args["end_x"], args["end_y"])
    duration_ms = args.get("duration_ms")
    device_mod = _get_device_module(daemon)
    device_mod.swipe(sx, sy, ex, ey, duration_ms=duration_ms, device_id=device_id)
    return ok_response({"start": [sx, sy], "end": [ex, ey]})


@_register("type")
def _cmd_type(args: dict, daemon: Any) -> str:
    text = args.get("text", "")
    device_id = _get_device_id(args, daemon)
    device_type = _get_device_type(daemon)

    if device_type == "adb":
        from phone_cli import adb
        original_ime = adb.detect_and_set_adb_keyboard(device_id=device_id)
        try:
            adb.clear_text(device_id=device_id)
            adb.type_text(text, device_id=device_id)
        finally:
            adb.restore_keyboard(original_ime, device_id=device_id)
    elif device_type == "hdc":
        from phone_cli import hdc
        hdc.type_text(text, device_id=device_id)
    elif device_type == "ios":
        from phone_cli import ios
        ios.clear_text(device_id=device_id)
        ios.type_text(text, device_id=device_id)
    else:
        # For iOS and others, use the device module's type_text directly
        module = _get_device_module(daemon)
        module.type_text(text, device_id=device_id)

    return ok_response({"typed": text})


@_register("back")
def _cmd_back(args: dict, daemon: Any) -> str:
    device_id = _get_device_id(args, daemon)
    device_mod = _get_device_module(daemon)
    device_mod.back(device_id=device_id)
    return ok_response({})


@_register("home")
def _cmd_home(args: dict, daemon: Any) -> str:
    device_id = _get_device_id(args, daemon)
    device_mod = _get_device_module(daemon)
    device_mod.home(device_id=device_id)
    return ok_response({})


@_register("launch")
def _cmd_launch(args: dict, daemon: Any) -> str:
    app_name = args.get("app_name", "")
    device_id = _get_device_id(args, daemon)
    device_mod = _get_device_module(daemon)
    success = device_mod.launch_app(app_name, device_id=device_id)
    if not success:
        return error_response(ErrorCode.APP_NOT_FOUND, f"App not found: {app_name}")
    return ok_response({"app_name": app_name})


@_register("get_current_app")
def _cmd_get_current_app(args: dict, daemon: Any) -> str:
    device_id = _get_device_id(args, daemon)
    device_mod = _get_device_module(daemon)
    app_name = device_mod.get_current_app(device_id=device_id)
    return ok_response({"app_name": app_name})


@_register("ui_tree")
def _cmd_ui_tree(args: dict, daemon: Any) -> str:
    device_id = _get_device_id(args, daemon)
    device_type = _get_device_type(daemon)

    try:
        if device_type == "adb":
            return _ui_tree_adb(device_id)
        elif device_type == "hdc":
            return _ui_tree_hdc(device_id)
        elif device_type == "ios":
            return _ui_tree_ios(device_id)
        else:
            return error_response(
                ErrorCode.UI_TREE_UNAVAILABLE,
                f"UI tree not supported for device type: {device_type}",
            )
    except Exception as e:
        return error_response(ErrorCode.UI_TREE_UNAVAILABLE, str(e))


def _ui_tree_adb(device_id: str | None) -> str:
    """Dump UI tree via ADB uiautomator."""
    adb_prefix = ["adb"]
    if device_id:
        adb_prefix = ["adb", "-s", device_id]

    # Dump UI hierarchy
    subprocess.run(
        adb_prefix + ["shell", "uiautomator", "dump", "/sdcard/ui_dump.xml"],
        capture_output=True, text=True, timeout=10,
    )

    # Read the dump
    result = subprocess.run(
        adb_prefix + ["shell", "cat", "/sdcard/ui_dump.xml"],
        capture_output=True, text=True, timeout=10,
    )

    if result.returncode != 0 or not result.stdout.strip():
        return error_response(ErrorCode.UI_TREE_UNAVAILABLE, "Failed to dump UI tree")

    # Parse XML to JSON elements
    try:
        elements = _parse_ui_xml(result.stdout)
        return ok_response({"elements": elements})
    except Exception as e:
        return error_response(ErrorCode.UI_TREE_UNAVAILABLE, f"XML parse error: {e}")


def _parse_ui_xml(xml_str: str) -> list[dict]:
    """Parse uiautomator XML dump into a list of element dicts."""
    elements = []
    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError:
        return elements

    for node in root.iter("node"):
        elem = {
            "text": node.get("text", ""),
            "resource_id": node.get("resource-id", ""),
            "class": node.get("class", ""),
            "bounds": node.get("bounds", ""),
        }
        elements.append(elem)
    return elements


def _ui_tree_hdc(device_id: str | None) -> str:
    """Dump UI tree via HDC uitest."""
    hdc_prefix = ["hdc"]
    if device_id:
        hdc_prefix = ["hdc", "-t", device_id]

    result = subprocess.run(
        hdc_prefix + ["shell", "uitest", "dumpLayout"],
        capture_output=True, text=True, timeout=10,
    )

    if result.returncode != 0:
        return error_response(ErrorCode.UI_TREE_UNAVAILABLE, "Failed to dump UI tree")

    return ok_response({"raw": result.stdout})


def _ui_tree_ios(device_id: str | None) -> str:
    """Dump UI tree via WDA source endpoint."""
    from phone_cli.ios.connection import get_wda_client

    client = get_wda_client(device_id)
    xml_str = client.source(format="xml")

    if not xml_str:
        return error_response(ErrorCode.UI_TREE_UNAVAILABLE, "Failed to dump iOS UI tree")

    try:
        elements = _parse_ios_ui_xml(xml_str)
        return ok_response({"elements": elements})
    except Exception as e:
        return error_response(ErrorCode.UI_TREE_UNAVAILABLE, f"XML parse error: {e}")


def _parse_ios_ui_xml(xml_str: str) -> list[dict]:
    """Parse WDA accessibility XML into a list of element dicts."""
    elements = []
    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError:
        return elements

    for node in root.iter():
        # Skip the root hierarchy node
        if node.tag in ("AppiumAUT", "hierarchy"):
            continue
        elem = {
            "type": node.get("type", node.tag),
            "name": node.get("name", ""),
            "label": node.get("label", ""),
            "value": node.get("value", ""),
            "visible": node.get("visible", ""),
            "enabled": node.get("enabled", ""),
            "x": node.get("x", ""),
            "y": node.get("y", ""),
            "width": node.get("width", ""),
            "height": node.get("height", ""),
        }
        # Only include elements that have at least some identifying info
        if elem["name"] or elem["label"] or elem["value"] or elem["type"]:
            elements.append(elem)
    return elements


@_register("clean_screenshots")
def _cmd_clean_screenshots(args: dict, daemon: Any) -> str:
    screenshot_dir = daemon.screenshot_dir
    if not os.path.exists(screenshot_dir):
        return ok_response({"removed": 0})

    clean_all = args.get("all", False)
    max_age_days = args.get("max_age_days", 7)
    now = time.time()
    removed = 0

    for filename in os.listdir(screenshot_dir):
        filepath = os.path.join(screenshot_dir, filename)
        if not os.path.isfile(filepath):
            continue
        if clean_all:
            os.remove(filepath)
            removed += 1
        else:
            age_days = (now - os.path.getmtime(filepath)) / 86400
            if age_days > max_age_days:
                os.remove(filepath)
                removed += 1

    return ok_response({"removed": removed})


@_register("log")
def _cmd_log(args: dict, daemon: Any) -> str:
    log_file = os.path.join(daemon.log_dir, "phone-cli.log")
    lines_count = args.get("lines", 50)
    task_id = args.get("task_id")

    if not os.path.exists(log_file):
        return ok_response({"entries": []})

    with open(log_file, "r", encoding="utf-8") as f:
        all_lines = f.readlines()

    # Filter by task_id if provided
    if task_id:
        all_lines = [l for l in all_lines if task_id in l]

    # Take last N lines
    entries = [l.rstrip("\n") for l in all_lines[-lines_count:]]
    return ok_response({"entries": entries})


# ── New commands: reduce screenshot frequency ─────────────────────────

@_register("app_state")
def _cmd_app_state(args: dict, daemon: Any) -> str:
    """Get app foreground state without taking a screenshot."""
    device_type = _get_device_type(daemon)
    if device_type != "adb":
        return error_response(
            ErrorCode.COMMAND_FAILED,
            f"app_state is only supported for ADB devices, current: {device_type}",
        )
    device_id = _get_device_id(args, daemon)
    from phone_cli.adb.device import get_app_state
    package = args.get("package")
    result = get_app_state(package=package, device_id=device_id)
    return ok_response(result)


@_register("wait_for_app")
def _cmd_wait_for_app(args: dict, daemon: Any) -> str:
    """Wait for an app to reach a target state with polling."""
    device_type = _get_device_type(daemon)
    if device_type != "adb":
        return error_response(
            ErrorCode.COMMAND_FAILED,
            f"wait_for_app is only supported for ADB devices, current: {device_type}",
        )
    device_id = _get_device_id(args, daemon)
    package = args.get("package")
    if not package:
        return error_response(ErrorCode.COMMAND_FAILED, "package is required")
    timeout = args.get("timeout", 30)
    target_state = args.get("state", "resumed")
    from phone_cli.adb.device import wait_for_app
    try:
        result = wait_for_app(
            package=package, timeout=timeout,
            target_state=target_state, device_id=device_id,
        )
        return ok_response(result)
    except TimeoutError as e:
        return error_response(ErrorCode.APP_NOT_RUNNING, str(e))


@_register("check_screen")
def _cmd_check_screen(args: dict, daemon: Any) -> str:
    """Check screen health (all-black/all-white detection)."""
    device_type = _get_device_type(daemon)
    if device_type != "adb":
        return error_response(
            ErrorCode.COMMAND_FAILED,
            f"check_screen is only supported for ADB devices, current: {device_type}",
        )
    device_id = _get_device_id(args, daemon)
    threshold = args.get("threshold", 0.95)
    from phone_cli.adb.device import check_screen_health
    try:
        result = check_screen_health(threshold=threshold, device_id=device_id)
        return ok_response(result)
    except Exception as e:
        return error_response(ErrorCode.SCREEN_CHECK_FAILED, str(e))


@_register("app_log")
def _cmd_app_log(args: dict, daemon: Any) -> str:
    """Get app logs via adb logcat."""
    device_type = _get_device_type(daemon)
    if device_type != "adb":
        return error_response(
            ErrorCode.COMMAND_FAILED,
            f"app_log is only supported for ADB devices, current: {device_type}",
        )
    device_id = _get_device_id(args, daemon)
    from phone_cli.adb.device import get_app_log
    package = args.get("package")
    filter_type = args.get("filter", "all")
    lines = args.get("lines", 20)
    result = get_app_log(
        package=package, filter_type=filter_type,
        lines=lines, device_id=device_id,
    )
    return ok_response(result)


@_register("install")
def _cmd_install(args: dict, daemon: Any) -> str:
    """Install APK and optionally launch it."""
    device_type = _get_device_type(daemon)
    if device_type != "adb":
        return error_response(
            ErrorCode.COMMAND_FAILED,
            f"install is only supported for ADB devices, current: {device_type}",
        )
    device_id = _get_device_id(args, daemon)
    apk_path = args.get("apk_path")
    if not apk_path:
        return error_response(ErrorCode.COMMAND_FAILED, "apk_path is required")
    launch = args.get("launch", False)
    from phone_cli.adb.device import install_apk
    try:
        result = install_apk(apk_path=apk_path, launch=launch, device_id=device_id)
        return ok_response(result)
    except FileNotFoundError as e:
        return error_response(ErrorCode.INSTALL_FAILED, str(e))
    except RuntimeError as e:
        return error_response(ErrorCode.INSTALL_FAILED, str(e))
