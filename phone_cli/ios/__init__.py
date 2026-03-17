"""iOS utilities for device interaction via tidevice + WDA."""

from phone_cli.ios.connection import (
    DeviceInfo,
    WDAConnection,
    get_wda_client,
    list_devices,
    quick_connect,
)
from phone_cli.ios.device import (
    back,
    double_tap,
    get_current_app,
    home,
    launch_app,
    long_press,
    swipe,
    tap,
)
from phone_cli.ios.input import (
    clear_text,
    type_text,
)
from phone_cli.ios.screenshot import get_screenshot

__all__ = [
    # Screenshot
    "get_screenshot",
    # Input
    "type_text",
    "clear_text",
    # Device control
    "get_current_app",
    "tap",
    "swipe",
    "back",
    "home",
    "double_tap",
    "long_press",
    "launch_app",
    # Connection management
    "WDAConnection",
    "DeviceInfo",
    "get_wda_client",
    "quick_connect",
    "list_devices",
]
