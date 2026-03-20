"""ADB utilities for Android device interaction."""

from phone_cli.adb.connection import (
    ADBConnection,
    ConnectionType,
    DeviceInfo,
    list_devices,
    quick_connect,
)
from phone_cli.adb.device import (
    back,
    check_screen_health,
    double_tap,
    get_app_log,
    get_app_state,
    get_current_app,
    home,
    install_apk,
    launch_app,
    long_press,
    swipe,
    tap,
    wait_for_app,
)
from phone_cli.adb.input import (
    clear_text,
    detect_and_set_adb_keyboard,
    restore_keyboard,
    type_text,
)
from phone_cli.adb.screenshot import get_screenshot

__all__ = [
    # Screenshot
    "get_screenshot",
    # Input
    "type_text",
    "clear_text",
    "detect_and_set_adb_keyboard",
    "restore_keyboard",
    # Device control
    "get_current_app",
    "get_app_state",
    "wait_for_app",
    "check_screen_health",
    "get_app_log",
    "install_apk",
    "tap",
    "swipe",
    "back",
    "home",
    "double_tap",
    "long_press",
    "launch_app",
    # Connection management
    "ADBConnection",
    "DeviceInfo",
    "ConnectionType",
    "quick_connect",
    "list_devices",
]
