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
from phone_cli.ios.runtime.base import UnsupportedOperationError


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
    except UnsupportedOperationError as e:
        return error_response(ErrorCode.UNSUPPORTED_OPERATION, str(e))
    except Exception as e:
        return error_response(ErrorCode.COMMAND_FAILED, str(e))


# ── Helpers ───────────────────────────────────────────────────────────

def _get_device_module(daemon: Any):
    """Return the adb, hdc, or ios module based on daemon state."""
    state = _get_state(daemon)
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


def _get_state(daemon: Any) -> dict[str, Any]:
    """Read daemon state once for the current command."""

    return daemon._read_state()


def _get_target_id(args: dict, daemon: Any) -> str | None:
    """Get target ID from args or daemon state."""

    state = _get_state(daemon)
    device_id = args.get("device_id")
    if device_id:
        return device_id
    if state.get("device_type") == "ios":
        return state.get("target_id") or state.get("device_id")
    return state.get("device_id")


def _get_screen_size(daemon: Any) -> tuple[int, int]:
    """Get screen size from daemon state or refresh it from the active backend."""

    state = _get_state(daemon)
    device_type = state.get("device_type", "adb")
    target_id = state.get("target_id") or state.get("device_id")
    size = state.get("screen_size")

    if device_type == "ios" and size == [1080, 2400]:
        from phone_cli import ios

        if target_id:
            try:
                width, height = ios.get_screen_size(device_id=target_id, state=state)
                size = [width, height]
                state["screen_size"] = size
                daemon._write_state(state)
            except Exception:
                pass
    elif device_type == "adb":
        from phone_cli import adb

        try:
            width, height = adb.get_screen_size(device_id=target_id)
            size = [width, height]
            if state.get("screen_size") != size:
                state["screen_size"] = size
                daemon._write_state(state)
        except Exception:
            pass

    if not size:
        size = [1080, 2400]
    return size[0], size[1]


def _get_device_type(daemon: Any) -> str:
    """Get device_type from daemon state."""
    state = _get_state(daemon)
    return state.get("device_type", "adb")


def _call_device_method(
    daemon: Any,
    method_name: str,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """Call a method on the active device module/backend."""

    device_mod = _get_device_module(daemon)
    state = _get_state(daemon)
    if state.get("device_type") == "ios":
        kwargs["state"] = state
    method = getattr(device_mod, method_name)
    return method(*args, **kwargs)


def _try_companion(
    method_name: str,
    forced_type: str | None = None,
    **kwargs: Any,
) -> dict | None:
    """Try companion accessibility service first unless forced to ADB.

    Returns the companion result dict on success, or None to signal fallback.
    """
    if forced_type == "adb":
        return None
    try:
        from phone_cli.adb.companion import CompanionClient, CompanionUnavailableError  # noqa: F811
        client = CompanionClient()
        if client.is_ready():
            method = getattr(client, method_name)
            result = method(**kwargs)
            if result.get("success"):
                return result
    except Exception:  # noqa: BLE001
        pass
    return None


def _companion_client_or_error() -> tuple[Any | None, str | None]:
    """Return a ready companion client or an error response payload."""
    try:
        from phone_cli.adb.companion import CompanionClient, CompanionUnavailableError

        client = CompanionClient()
        if not client.is_ready():
            return None, error_response(
                ErrorCode.COMPANION_UNAVAILABLE,
                "Companion accessibility service is not ready",
            )
        return client, None
    except CompanionUnavailableError as e:
        return None, error_response(ErrorCode.COMPANION_UNAVAILABLE, str(e))


def _sync_ios_state(
    daemon: Any,
    device_id: str | None,
    *,
    bundle_id: str | None = None,
) -> None:
    """Persist the latest iOS runtime state derived from the active backend."""

    state = _get_state(daemon)
    if state.get("device_type") != "ios":
        return

    try:
        from phone_cli import ios

        runtime = state.get("ios_runtime")
        backend = ios.get_backend(state=state)

        resolved_bundle_id = bundle_id
        getter = getattr(backend, "get_bound_bundle_id", None)
        if callable(getter):
            backend_bundle_id = getter(device_id)
            if backend_bundle_id is not None:
                resolved_bundle_id = backend_bundle_id
        state["bundle_id"] = resolved_bundle_id

        getter = getattr(backend, "get_bound_window_id", None)
        if callable(getter):
            state["window_id"] = getter(device_id)

        should_refresh_screen_size = (
            runtime != "app_on_mac" or state.get("window_id") is not None
        )
        if should_refresh_screen_size:
            try:
                width, height = ios.get_screen_size(device_id=device_id, state=state)
                state["screen_size"] = [width, height]
            except Exception:
                pass

        if runtime:
            state["capabilities"] = ios.get_capabilities(state=state)
        daemon._write_state(state)
    except Exception:
        pass


# ── Command handlers ─────────────────────────────────────────────────

@_register("status")
def _cmd_status(args: dict, daemon: Any) -> str:
    return ok_response(daemon.status())


@_register("devices")
def _cmd_devices(args: dict, daemon: Any) -> str:
    device_type = _get_device_type(daemon)
    state = _get_state(daemon)
    devices = _call_device_method(daemon, "list_devices")
    device_list = []
    for d in devices:
        item = {
            "device_id": d.device_id,
            "model": getattr(d, "model", ""),
            "status": getattr(d, "status", ""),
        }
        if device_type == "ios":
            item.update(
                {
                    "target_id": getattr(d, "target_id", d.device_id),
                    "runtime": getattr(d, "runtime", state.get("ios_runtime")),
                    "name": getattr(d, "name", getattr(d, "model", "")),
                }
            )
        device_list.append(item)
    payload = {"devices": device_list}
    if device_type == "ios":
        payload["ios_runtime"] = state.get("ios_runtime")
    return ok_response(payload)


@_register("detect_runtimes")
def _cmd_detect_runtimes(args: dict, daemon: Any) -> str:
    device_type = args.get("device_type", "ios")
    if device_type != "ios":
        return error_response(
            ErrorCode.RUNTIME_NOT_SUPPORTED,
            f"detect_runtimes is only supported for iOS, current: {device_type}",
        )

    from phone_cli.ios.runtime.discovery import detect_ios_runtimes, resolve_runtime_selection

    result = detect_ios_runtimes()
    payload = result.to_dict()
    payload["selection"] = resolve_runtime_selection(result).to_dict()
    return ok_response(payload)


@_register("set_device")
def _cmd_set_device(args: dict, daemon: Any) -> str:
    device_id = args.get("device_id")
    state = _get_state(daemon)
    state["device_id"] = device_id
    if state.get("device_type") == "ios":
        state["target_id"] = device_id
    else:
        # Android / HarmonyOS should not keep a stale target_id from
        # a previously selected emulator or legacy state.
        state["target_id"] = device_id
    daemon._write_state(state)
    return ok_response({
        "device_id": state.get("device_id"),
        "target_id": state.get("target_id"),
    })


@_register("device_info")
def _cmd_device_info(args: dict, daemon: Any) -> str:
    state = _get_state(daemon)
    if state.get("device_type") == "ios":
        _sync_ios_state(
            daemon,
            state.get("target_id") or state.get("device_id"),
            bundle_id=state.get("bundle_id"),
        )
    state = _get_state(daemon)
    payload = {
        "device_type": state.get("device_type"),
        "device_id": state.get("device_id"),
        "target_id": state.get("target_id"),
        "screen_size": state.get("screen_size"),
        "device_status": state.get("device_status"),
    }
    if state.get("device_type") == "ios":
        payload.update(
            {
                "ios_runtime": state.get("ios_runtime"),
                "bundle_id": state.get("bundle_id"),
                "window_id": state.get("window_id"),
                "capabilities": state.get("capabilities"),
            }
        )
    return ok_response(payload)


@_register("screenshot")
def _cmd_screenshot(args: dict, daemon: Any) -> str:
    device_id = _get_target_id(args, daemon)
    try:
        screenshot = _call_device_method(
            daemon,
            "get_screenshot",
            device_id=device_id,
        )
    except Exception as e:
        return error_response(ErrorCode.SCREENSHOT_FAILED, str(e))
    if _get_device_type(daemon) == "ios":
        _sync_ios_state(
            daemon,
            device_id,
            bundle_id=_get_state(daemon).get("bundle_id"),
        )

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
    device_id = _get_target_id(args, daemon)
    w, h = _get_screen_size(daemon)
    conv = CoordConverter(w, h)
    x, y = conv.to_absolute(args["x"], args["y"])
    device_type = _get_device_type(daemon)
    if device_type == "adb":
        result = _try_companion("tap", forced_type=args.get("type"), x=x, y=y)
        if result is not None:
            return ok_response({"x": x, "y": y, "source": "companion"})
    _call_device_method(daemon, "tap", x, y, device_id=device_id)
    return ok_response({"x": x, "y": y, "source": "adb"})


@_register("double_tap")
def _cmd_double_tap(args: dict, daemon: Any) -> str:
    device_id = _get_target_id(args, daemon)
    w, h = _get_screen_size(daemon)
    conv = CoordConverter(w, h)
    x, y = conv.to_absolute(args["x"], args["y"])
    device_type = _get_device_type(daemon)
    if device_type == "adb":
        result = _try_companion("double_tap", forced_type=args.get("type"), x=x, y=y)
        if result is not None:
            return ok_response({"x": x, "y": y, "source": "companion"})
    _call_device_method(daemon, "double_tap", x, y, device_id=device_id)
    return ok_response({"x": x, "y": y, "source": "adb"})


@_register("long_press")
def _cmd_long_press(args: dict, daemon: Any) -> str:
    device_id = _get_target_id(args, daemon)
    w, h = _get_screen_size(daemon)
    conv = CoordConverter(w, h)
    x, y = conv.to_absolute(args["x"], args["y"])
    device_type = _get_device_type(daemon)
    if device_type == "adb":
        result = _try_companion("long_press", forced_type=args.get("type"), x=x, y=y)
        if result is not None:
            return ok_response({"x": x, "y": y, "source": "companion"})
    _call_device_method(daemon, "long_press", x, y, device_id=device_id)
    return ok_response({"x": x, "y": y, "source": "adb"})


@_register("swipe")
def _cmd_swipe(args: dict, daemon: Any) -> str:
    device_id = _get_target_id(args, daemon)
    w, h = _get_screen_size(daemon)
    conv = CoordConverter(w, h)
    sx, sy = conv.to_absolute(args["start_x"], args["start_y"])
    ex, ey = conv.to_absolute(args["end_x"], args["end_y"])
    duration_ms = args.get("duration_ms")
    device_type = _get_device_type(daemon)
    if device_type == "adb":
        companion_kwargs: dict[str, Any] = {
            "start_x": sx, "start_y": sy, "end_x": ex, "end_y": ey,
        }
        if duration_ms is not None:
            companion_kwargs["duration_ms"] = duration_ms
        result = _try_companion("swipe", forced_type=args.get("type"), **companion_kwargs)
        if result is not None:
            return ok_response({"start": [sx, sy], "end": [ex, ey], "source": "companion"})
    _call_device_method(
        daemon,
        "swipe",
        sx,
        sy,
        ex,
        ey,
        duration_ms=duration_ms,
        device_id=device_id,
    )
    return ok_response({"start": [sx, sy], "end": [ex, ey], "source": "adb"})


@_register("type")
def _cmd_type(args: dict, daemon: Any) -> str:
    text = args.get("text", "")
    device_id = _get_target_id(args, daemon)
    device_type = _get_device_type(daemon)

    if device_type == "adb":
        # Try companion set_text first (faster, no keyboard switching)
        result = _try_companion("set_text", forced_type=args.get("type"), text=text)
        if result is not None:
            return ok_response({"typed": text, "source": "companion"})

        # Fall back to ADB keyboard flow
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
        state = _get_state(daemon)
        capabilities = state.get("capabilities") or ios.get_capabilities(state=state)
        if capabilities.get("clear_text"):
            ios.clear_text(device_id=device_id, state=state)
        ios.type_text(text, device_id=device_id, state=state)
    else:
        # For iOS and others, use the device module's type_text directly
        _call_device_method(daemon, "type_text", text, device_id=device_id)

    return ok_response({"typed": text})


@_register("back")
def _cmd_back(args: dict, daemon: Any) -> str:
    device_id = _get_target_id(args, daemon)
    device_type = _get_device_type(daemon)
    if device_type == "adb":
        result = _try_companion("back", forced_type=args.get("type"))
        if result is not None:
            return ok_response({"source": "companion"})
    _call_device_method(daemon, "back", device_id=device_id)
    return ok_response({"source": "adb"})


@_register("home")
def _cmd_home(args: dict, daemon: Any) -> str:
    device_id = _get_target_id(args, daemon)
    device_type = _get_device_type(daemon)
    if device_type == "adb":
        result = _try_companion("home", forced_type=args.get("type"))
        if result is not None:
            return ok_response({"source": "companion"})
    _call_device_method(daemon, "home", device_id=device_id)
    return ok_response({"source": "adb"})


@_register("launch")
def _cmd_launch(args: dict, daemon: Any) -> str:
    app_name = args.get("app_name")
    bundle_id = args.get("bundle_id")
    app_path = args.get("app_path")
    if not any([app_name, bundle_id, app_path]):
        return error_response(ErrorCode.COMMAND_FAILED, "app_name, bundle_id, or app_path is required")

    device_id = _get_target_id(args, daemon)
    device_type = _get_device_type(daemon)
    if device_type == "ios":
        success = _call_device_method(
            daemon,
            "launch_app",
            app_name=app_name,
            bundle_id=bundle_id,
            app_path=app_path,
            device_id=device_id,
        )
    else:
        success = _call_device_method(
            daemon,
            "launch_app",
            app_name or "",
            device_id=device_id,
        )
    if not success:
        app_identifier = bundle_id or app_path or app_name or "<unknown>"
        return error_response(ErrorCode.APP_NOT_FOUND, f"App not found: {app_identifier}")
    if device_type == "ios":
        _sync_ios_state(daemon, device_id, bundle_id=bundle_id)
    return ok_response(
        {
            "app_name": app_name,
            "bundle_id": bundle_id,
            "app_path": app_path,
        }
    )


@_register("get_current_app")
def _cmd_get_current_app(args: dict, daemon: Any) -> str:
    device_id = _get_target_id(args, daemon)
    app_name = _call_device_method(daemon, "get_current_app", device_id=device_id)
    if _get_device_type(daemon) == "ios":
        _sync_ios_state(
            daemon,
            device_id,
            bundle_id=_get_state(daemon).get("bundle_id"),
        )
    return ok_response({"app_name": app_name})


@_register("ui_tree")
def _cmd_ui_tree(args: dict, daemon: Any) -> str:
    device_id = _get_target_id(args, daemon)
    device_type = _get_device_type(daemon)

    try:
        if device_type == "adb":
            return _ui_tree_adb(device_id)
        elif device_type == "hdc":
            return _ui_tree_hdc(device_id)
        elif device_type == "ios":
            try:
                result = _call_device_method(daemon, "ui_tree", device_id=device_id)
                _sync_ios_state(
                    daemon,
                    device_id,
                    bundle_id=_get_state(daemon).get("bundle_id"),
                )
                return ok_response(result)
            except UnsupportedOperationError as e:
                return error_response(ErrorCode.UI_TREE_UNAVAILABLE, str(e))
        else:
            return error_response(
                ErrorCode.UI_TREE_UNAVAILABLE,
                f"UI tree not supported for device type: {device_type}",
            )
    except Exception as e:
        return error_response(ErrorCode.UI_TREE_UNAVAILABLE, str(e))


def _ui_tree_adb(device_id: str | None) -> str:
    """Dump UI tree via Companion (preferred) or ADB uiautomator (fallback)."""

    # 1. Try companion service first
    try:
        from phone_cli.adb.companion import CompanionClient, CompanionUnavailableError
        client = CompanionClient()
        if client.is_ready():
            tree = client.get_ui_tree()
            elements = _normalize_companion_tree(tree)
            return ok_response({"elements": elements, "source": "companion"})
    except (CompanionUnavailableError, OSError, ValueError, KeyError):
        pass  # Fall through to uiautomator

    # 2. Fall back to uiautomator dump
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
        return ok_response({"elements": elements, "source": "uiautomator"})
    except Exception as e:
        return error_response(ErrorCode.UI_TREE_UNAVAILABLE, f"XML parse error: {e}")


def _normalize_companion_tree(tree: dict) -> list[dict]:
    """Flatten the companion hierarchical UiNode tree into a list of element dicts.

    The output format is compatible with _parse_ui_xml but includes additional
    companion-specific fields (node_id, content_description, clickable, etc.).
    """
    elements: list[dict] = []

    def _flatten(node: dict) -> None:
        bounds = node.get("bounds")
        bounds_str = ""
        center_x = None
        center_y = None
        if bounds:
            left = bounds.get("left", 0)
            top = bounds.get("top", 0)
            right = bounds.get("right", 0)
            bottom = bounds.get("bottom", 0)
            bounds_str = f"[{left},{top}][{right},{bottom}]"
            center_x = (left + right) // 2
            center_y = (top + bottom) // 2

        center = node.get("center")
        if center:
            center_x = center.get("x", center_x)
            center_y = center.get("y", center_y)

        elem = {
            "text": node.get("text", ""),
            "resource_id": node.get("resourceId", ""),
            "class": node.get("className", ""),
            "bounds": bounds_str,
            # Companion-enhanced fields
            "node_id": node.get("nodeId", ""),
            "content_description": node.get("contentDescription", ""),
            "clickable": node.get("clickable", False),
            "scrollable": node.get("scrollable", False),
            "editable": node.get("editable", False),
        }
        if center_x is not None:
            elem["center_x"] = center_x
        if center_y is not None:
            elem["center_y"] = center_y

        # Only include nodes that have some identifying info
        has_info = (
            elem["text"]
            or elem["resource_id"]
            or elem["content_description"]
            or elem["clickable"]
            or elem["scrollable"]
            or elem["editable"]
        )
        if has_info:
            elements.append(elem)

        for child in node.get("children", []):
            _flatten(child)

    root = tree.get("root")
    if root:
        _flatten(root)

    return elements


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
    device_id = _get_target_id(args, daemon)
    bundle_id = args.get("bundle_id") or args.get("package")
    if device_type == "adb":
        from phone_cli.adb.device import get_app_state

        result = get_app_state(package=bundle_id, device_id=device_id)
        return ok_response(result)
    if device_type == "ios":
        result = _call_device_method(
            daemon,
            "app_state",
            bundle_id=bundle_id,
            device_id=device_id,
        )
        _sync_ios_state(daemon, device_id, bundle_id=bundle_id)
        return ok_response(result)
    return error_response(
        ErrorCode.UNSUPPORTED_OPERATION,
        f"app_state is not supported for device type: {device_type}",
    )


@_register("wait_for_app")
def _cmd_wait_for_app(args: dict, daemon: Any) -> str:
    """Wait for an app to reach a target state with polling."""
    device_type = _get_device_type(daemon)
    device_id = _get_target_id(args, daemon)
    bundle_id = args.get("bundle_id") or args.get("package")
    if not bundle_id:
        return error_response(ErrorCode.COMMAND_FAILED, "package or bundle_id is required")
    timeout = args.get("timeout", 30)
    target_state = args.get("state", "resumed")
    try:
        if device_type == "adb":
            from phone_cli.adb.device import wait_for_app

            result = wait_for_app(
                package=bundle_id,
                timeout=timeout,
                target_state=target_state,
                device_id=device_id,
            )
            return ok_response(result)
        if device_type == "ios":
            result = _call_device_method(
                daemon,
                "wait_for_app",
                bundle_id=bundle_id,
                timeout=timeout,
                wait_state=target_state,
                device_id=device_id,
            )
            _sync_ios_state(daemon, device_id, bundle_id=bundle_id)
            return ok_response(result)
        return error_response(
            ErrorCode.UNSUPPORTED_OPERATION,
            f"wait_for_app is not supported for device type: {device_type}",
        )
    except TimeoutError as e:
        return error_response(ErrorCode.APP_NOT_RUNNING, str(e))


@_register("check_screen")
def _cmd_check_screen(args: dict, daemon: Any) -> str:
    """Check screen health (all-black/all-white detection)."""
    device_type = _get_device_type(daemon)
    device_id = _get_target_id(args, daemon)
    threshold = args.get("threshold", 0.95)
    try:
        if device_type == "adb":
            from phone_cli.adb.device import check_screen_health

            result = check_screen_health(threshold=threshold, device_id=device_id)
            return ok_response(result)
        if device_type == "ios":
            result = _call_device_method(
                daemon,
                "check_screen",
                threshold=threshold,
                device_id=device_id,
            )
            return ok_response(result)
        return error_response(
            ErrorCode.UNSUPPORTED_OPERATION,
            f"check_screen is not supported for device type: {device_type}",
        )
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
    device_id = _get_target_id(args, daemon)
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
    device_id = _get_target_id(args, daemon)
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


# ── Companion commands (Android-only) ────────────────────────────────

@_register("companion_status")
def _cmd_companion_status(args: dict, daemon: Any) -> str:
    """Check companion installation, accessibility, and readiness status."""
    device_type = _get_device_type(daemon)
    if device_type != "adb":
        return error_response(
            ErrorCode.UNSUPPORTED_OPERATION,
            "companion_status is only supported for Android (ADB) devices",
        )
    device_id = _get_target_id(args, daemon)
    from phone_cli.adb.companion_manager import CompanionManager
    manager = CompanionManager(device_id=device_id)
    status = manager.get_status()
    return ok_response(status)


@_register("companion_preflight")
def _cmd_companion_preflight(args: dict, daemon: Any) -> str:
    """Run the Android companion preflight checks and return actionable diagnostics."""
    device_type = _get_device_type(daemon)
    if device_type != "adb":
        return error_response(
            ErrorCode.UNSUPPORTED_OPERATION,
            "companion_preflight is only supported for Android (ADB) devices",
        )
    device_id = _get_target_id(args, daemon)
    from phone_cli.adb.companion_manager import CompanionManager

    manager = CompanionManager(device_id=device_id)
    status = manager.get_status()
    return ok_response(status)


@_register("companion_setup")
def _cmd_companion_setup(args: dict, daemon: Any) -> str:
    """Build (if needed), install, enable accessibility, and set up port forwarding."""
    device_type = _get_device_type(daemon)
    if device_type != "adb":
        return error_response(
            ErrorCode.UNSUPPORTED_OPERATION,
            "companion_setup is only supported for Android (ADB) devices",
        )
    device_id = _get_target_id(args, daemon)
    from phone_cli.adb.companion_manager import CompanionManager
    manager = CompanionManager(device_id=device_id)
    try:
        result = manager.ensure_ready()
        if result.get("available"):
            # Write companion status to daemon state
            state = _get_state(daemon)
            state["companion_status"] = "ready"
            daemon._write_state(state)
        return ok_response(result)
    except (FileNotFoundError, EnvironmentError, RuntimeError, subprocess.TimeoutExpired) as e:
        return error_response(ErrorCode.COMPANION_BUILD_FAILED, str(e))


@_register("find_nodes")
def _cmd_find_nodes(args: dict, daemon: Any) -> str:
    """Search UI nodes by criteria via companion service."""
    device_type = _get_device_type(daemon)
    if device_type != "adb":
        return error_response(
            ErrorCode.UNSUPPORTED_OPERATION,
            "find_nodes is only supported for Android (ADB) devices",
        )
    from phone_cli.adb.companion import CompanionClient, CompanionUnavailableError
    try:
        client = CompanionClient()
        result = client.find_nodes(
            text=args.get("text"),
            text_contains=args.get("text_contains"),
            resource_id=args.get("resource_id"),
            class_name=args.get("class_name"),
            clickable=args.get("clickable"),
        )
        return ok_response(result)
    except CompanionUnavailableError as e:
        return error_response(ErrorCode.COMPANION_UNAVAILABLE, str(e))


@_register("search_click")
def _cmd_search_click(args: dict, daemon: Any) -> str:
    """Search a node via companion and click it in one request."""
    device_type = _get_device_type(daemon)
    if device_type != "adb":
        return error_response(
            ErrorCode.UNSUPPORTED_OPERATION,
            "search_click is only supported for Android (ADB) devices",
        )
    client, err = _companion_client_or_error()
    if err:
        return err
    result = client.search_and_click(
        text=args.get("text"),
        text_contains=args.get("text_contains"),
        resource_id=args.get("resource_id"),
        class_name=args.get("class_name"),
        package_name=args.get("package_name"),
        clickable=args.get("clickable"),
        index=args.get("index", 0),
    )
    return ok_response(result)


@_register("click_node")
def _cmd_click_node(args: dict, daemon: Any) -> str:
    """Click a UI node by nodeId with optional coordinate fallback."""
    device_type = _get_device_type(daemon)
    if device_type != "adb":
        return error_response(
            ErrorCode.UNSUPPORTED_OPERATION,
            "click_node is only supported for Android (ADB) devices",
        )
    node_id = args.get("node_id")
    if not node_id:
        return error_response(ErrorCode.COMMAND_FAILED, "node_id is required")
    from phone_cli.adb.companion import CompanionClient, CompanionUnavailableError
    try:
        client = CompanionClient()
        result = client.click_node(
            node_id=node_id,
            fallback_x=args.get("fallback_x"),
            fallback_y=args.get("fallback_y"),
        )
        return ok_response(result)
    except CompanionUnavailableError as e:
        return error_response(ErrorCode.COMPANION_UNAVAILABLE, str(e))


@_register("search_set_text")
def _cmd_search_set_text(args: dict, daemon: Any) -> str:
    """Search an input node via companion and set text in one request."""
    device_type = _get_device_type(daemon)
    if device_type != "adb":
        return error_response(
            ErrorCode.UNSUPPORTED_OPERATION,
            "search_set_text is only supported for Android (ADB) devices",
        )
    text = args.get("text")
    if text is None:
        return error_response(ErrorCode.COMMAND_FAILED, "text is required")
    client, err = _companion_client_or_error()
    if err:
        return err
    result = client.search_and_set_text(
        text=text,
        match_text=args.get("match_text"),
        text_contains=args.get("text_contains"),
        resource_id=args.get("resource_id"),
        class_name=args.get("class_name"),
        package_name=args.get("package_name"),
        index=args.get("index", 0),
        use_focused_fallback=args.get("use_focused_fallback", True),
    )
    return ok_response(result)


@_register("screen_context")
def _cmd_screen_context(args: dict, daemon: Any) -> str:
    """Get interactive elements summary from companion service."""
    device_type = _get_device_type(daemon)
    if device_type != "adb":
        return error_response(
            ErrorCode.UNSUPPORTED_OPERATION,
            "screen_context is only supported for Android (ADB) devices",
        )
    from phone_cli.adb.companion import CompanionClient, CompanionUnavailableError
    try:
        client = CompanionClient()
        result = client.get_screen_context()
        return ok_response(result)
    except CompanionUnavailableError as e:
        return error_response(ErrorCode.COMPANION_UNAVAILABLE, str(e))
