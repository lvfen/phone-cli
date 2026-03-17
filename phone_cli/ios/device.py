"""Device control utilities for iOS automation via WDA."""

import time
from typing import Optional

from phone_cli.config.apps_ios import APP_PACKAGES


def get_current_app(device_id: str | None = None) -> str:
    """
    Get the currently active app name.

    Args:
        device_id: Optional iOS device UDID.

    Returns:
        The app name if recognized, otherwise the bundle ID or "SpringBoard".
    """
    from phone_cli.ios.connection import get_wda_client

    client = get_wda_client(device_id)

    try:
        app_info = client.app_current()
        bundle_id = app_info.get("bundleId", "") if isinstance(app_info, dict) else getattr(app_info, "bundleId", "")

        if not bundle_id or bundle_id == "com.apple.springboard":
            return "SpringBoard"

        # Look up friendly name
        for app_name, pkg in APP_PACKAGES.items():
            if pkg == bundle_id:
                return app_name

        return bundle_id
    except Exception:
        return "SpringBoard"


def tap(
    x: int, y: int, device_id: str | None = None, delay: float | None = None
) -> None:
    """
    Tap at the specified coordinates.

    Args:
        x: X coordinate.
        y: Y coordinate.
        device_id: Optional iOS device UDID.
        delay: Delay in seconds after tap.
    """
    from phone_cli.ios.connection import get_wda_client

    if delay is None:
        delay = 0.5

    client = get_wda_client(device_id)
    client.click(x, y)
    time.sleep(delay)


def double_tap(
    x: int, y: int, device_id: str | None = None, delay: float | None = None
) -> None:
    """
    Double tap at the specified coordinates.

    Args:
        x: X coordinate.
        y: Y coordinate.
        device_id: Optional iOS device UDID.
        delay: Delay in seconds after double tap.
    """
    from phone_cli.ios.connection import get_wda_client

    if delay is None:
        delay = 0.5

    client = get_wda_client(device_id)
    client.double_click(x, y)
    time.sleep(delay)


def long_press(
    x: int,
    y: int,
    duration_ms: int = 3000,
    device_id: str | None = None,
    delay: float | None = None,
) -> None:
    """
    Long press at the specified coordinates.

    Args:
        x: X coordinate.
        y: Y coordinate.
        duration_ms: Duration of press in milliseconds.
        device_id: Optional iOS device UDID.
        delay: Delay in seconds after long press.
    """
    from phone_cli.ios.connection import get_wda_client

    if delay is None:
        delay = 0.5

    client = get_wda_client(device_id)
    duration_s = duration_ms / 1000.0
    client.long_click(x, y, duration_s)
    time.sleep(delay)


def swipe(
    start_x: int,
    start_y: int,
    end_x: int,
    end_y: int,
    duration_ms: int | None = None,
    device_id: str | None = None,
    delay: float | None = None,
) -> None:
    """
    Swipe from start to end coordinates.

    Args:
        start_x: Starting X coordinate.
        start_y: Starting Y coordinate.
        end_x: Ending X coordinate.
        end_y: Ending Y coordinate.
        duration_ms: Duration of swipe in milliseconds (auto-calculated if None).
        device_id: Optional iOS device UDID.
        delay: Delay in seconds after swipe.
    """
    from phone_cli.ios.connection import get_wda_client

    if delay is None:
        delay = 0.5

    client = get_wda_client(device_id)

    if duration_ms is None:
        dist_sq = (start_x - end_x) ** 2 + (start_y - end_y) ** 2
        duration_ms = int(dist_sq / 1000)
        duration_ms = max(1000, min(duration_ms, 2000))

    duration_s = duration_ms / 1000.0
    client.swipe(start_x, start_y, end_x, end_y, duration_s)
    time.sleep(delay)


def back(device_id: str | None = None, delay: float | None = None) -> None:
    """
    Simulate back navigation on iOS.

    iOS has no hardware back button, so this performs a left-edge swipe
    (swipe from left edge to right) to trigger the system back gesture.

    Args:
        device_id: Optional iOS device UDID.
        delay: Delay in seconds after the gesture.
    """
    from phone_cli.ios.connection import get_wda_client

    if delay is None:
        delay = 0.5

    client = get_wda_client(device_id)

    # Get window size for edge swipe
    try:
        window_size = client.window_size()
        w = window_size.width if hasattr(window_size, "width") else window_size[0]
        h = window_size.height if hasattr(window_size, "height") else window_size[1]
    except Exception:
        w, h = 390, 844  # iPhone 13/14 logical size fallback

    # Swipe from left edge (x=5) to center, at vertical midpoint
    mid_y = h // 2
    client.swipe(5, mid_y, w // 2, mid_y, 0.3)
    time.sleep(delay)


def home(device_id: str | None = None, delay: float | None = None) -> None:
    """
    Press the home button (or equivalent gesture on Face ID devices).

    Args:
        device_id: Optional iOS device UDID.
        delay: Delay in seconds after pressing home.
    """
    from phone_cli.ios.connection import get_wda_client

    if delay is None:
        delay = 0.5

    client = get_wda_client(device_id)
    client.home()
    time.sleep(delay)


def launch_app(
    app_name: str, device_id: str | None = None, delay: float | None = None
) -> bool:
    """
    Launch an app by name.

    Args:
        app_name: The app name (must be in APP_PACKAGES).
        device_id: Optional iOS device UDID.
        delay: Delay in seconds after launching.

    Returns:
        True if app was launched, False if app not found.
    """
    from phone_cli.ios.connection import get_wda_client

    if delay is None:
        delay = 2.0

    if app_name not in APP_PACKAGES:
        return False

    bundle_id = APP_PACKAGES[app_name]
    client = get_wda_client(device_id)
    client.app_launch(bundle_id)
    time.sleep(delay)
    return True
