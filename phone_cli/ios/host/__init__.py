"""Shared macOS host primitives for simulator and app_on_mac runtimes."""

from phone_cli.ios.host.ax_tree import AXNode, flatten_tree, read_window_tree
from phone_cli.ios.host.events import (
    click_point,
    double_click_point,
    drag_between,
    long_press_point,
    type_text,
)
from phone_cli.ios.host.permissions import (
    HostAutomationSupport,
    HostSupportReason,
    PermissionStatus,
    check_accessibility_permission,
    check_app_on_mac_host_support,
    check_simulator_host_support,
    check_screen_recording_permission,
    get_host_dependency_status,
)
from phone_cli.ios.host.screenshots import WindowScreenshot, capture_window
from phone_cli.ios.host.windows import (
    SIMULATOR_BUNDLE_ID,
    HostWindow,
    Rect,
    find_app_window,
    find_simulator_window,
    get_window,
    list_windows,
    map_device_point,
    map_relative_point,
)

__all__ = [
    "AXNode",
    "HostAutomationSupport",
    "HostSupportReason",
    "HostWindow",
    "PermissionStatus",
    "Rect",
    "WindowScreenshot",
    "capture_window",
    "check_accessibility_permission",
    "check_app_on_mac_host_support",
    "check_simulator_host_support",
    "check_screen_recording_permission",
    "click_point",
    "double_click_point",
    "drag_between",
    "find_app_window",
    "find_simulator_window",
    "flatten_tree",
    "get_host_dependency_status",
    "get_window",
    "long_press_point",
    "list_windows",
    "map_device_point",
    "map_relative_point",
    "read_window_tree",
    "SIMULATOR_BUNDLE_ID",
    "type_text",
]
