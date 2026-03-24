"""Device control utilities for Android automation."""

import os
import re
import subprocess
import time
from typing import List, Optional, Tuple

from phone_cli.config.apps import APP_PACKAGES
from phone_cli.config.timing import TIMING_CONFIG


def get_screen_size(device_id: str | None = None, timeout: int = 5) -> Tuple[int, int]:
    """
    Get the current logical display size used by ADB input commands.

    Prefers `wm size` override dimensions when present and swaps width/height
    for landscape rotations so relative 0-999 coordinates map to the visible
    screen orientation.
    """

    adb_prefix = _get_adb_prefix(device_id)
    result = subprocess.run(
        adb_prefix + ["shell", "wm", "size"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
    )
    output = (result.stdout or "") + "\n" + (result.stderr or "")
    width, height = _parse_wm_size(output)

    rotation = _get_display_rotation(device_id=device_id, timeout=timeout)
    if rotation in {1, 3}:
        width, height = height, width

    return width, height


def get_current_app(device_id: str | None = None) -> str:
    """
    Get the currently focused app name.

    Args:
        device_id: Optional ADB device ID for multi-device setups.

    Returns:
        The app name if recognized, otherwise "System Home".
    """
    adb_prefix = _get_adb_prefix(device_id)

    result = subprocess.run(
        adb_prefix + ["shell", "dumpsys", "window"], capture_output=True, text=True, encoding="utf-8"
    )
    output = result.stdout
    if not output:
        raise ValueError("No output from dumpsys window")

    # Parse window focus info
    for line in output.split("\n"):
        if "mCurrentFocus" in line or "mFocusedApp" in line:
            for app_name, package in APP_PACKAGES.items():
                if package in line:
                    return app_name

    return "System Home"


def tap(
    x: int, y: int, device_id: str | None = None, delay: float | None = None
) -> None:
    """
    Tap at the specified coordinates.

    Args:
        x: X coordinate.
        y: Y coordinate.
        device_id: Optional ADB device ID.
        delay: Delay in seconds after tap. If None, uses configured default.
    """
    if delay is None:
        delay = TIMING_CONFIG.device.default_tap_delay

    adb_prefix = _get_adb_prefix(device_id)

    subprocess.run(
        adb_prefix + ["shell", "input", "tap", str(x), str(y)], capture_output=True
    )
    time.sleep(delay)


def double_tap(
    x: int, y: int, device_id: str | None = None, delay: float | None = None
) -> None:
    """
    Double tap at the specified coordinates.

    Args:
        x: X coordinate.
        y: Y coordinate.
        device_id: Optional ADB device ID.
        delay: Delay in seconds after double tap. If None, uses configured default.
    """
    if delay is None:
        delay = TIMING_CONFIG.device.default_double_tap_delay

    adb_prefix = _get_adb_prefix(device_id)

    subprocess.run(
        adb_prefix + ["shell", "input", "tap", str(x), str(y)], capture_output=True
    )
    time.sleep(TIMING_CONFIG.device.double_tap_interval)
    subprocess.run(
        adb_prefix + ["shell", "input", "tap", str(x), str(y)], capture_output=True
    )
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
        device_id: Optional ADB device ID.
        delay: Delay in seconds after long press. If None, uses configured default.
    """
    if delay is None:
        delay = TIMING_CONFIG.device.default_long_press_delay

    adb_prefix = _get_adb_prefix(device_id)

    subprocess.run(
        adb_prefix
        + ["shell", "input", "swipe", str(x), str(y), str(x), str(y), str(duration_ms)],
        capture_output=True,
    )
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
        device_id: Optional ADB device ID.
        delay: Delay in seconds after swipe. If None, uses configured default.
    """
    if delay is None:
        delay = TIMING_CONFIG.device.default_swipe_delay

    adb_prefix = _get_adb_prefix(device_id)

    if duration_ms is None:
        # Calculate duration based on distance
        dist_sq = (start_x - end_x) ** 2 + (start_y - end_y) ** 2
        duration_ms = int(dist_sq / 1000)
        duration_ms = max(1000, min(duration_ms, 2000))  # Clamp between 1000-2000ms

    subprocess.run(
        adb_prefix
        + [
            "shell",
            "input",
            "swipe",
            str(start_x),
            str(start_y),
            str(end_x),
            str(end_y),
            str(duration_ms),
        ],
        capture_output=True,
    )
    time.sleep(delay)


def back(device_id: str | None = None, delay: float | None = None) -> None:
    """
    Press the back button.

    Args:
        device_id: Optional ADB device ID.
        delay: Delay in seconds after pressing back. If None, uses configured default.
    """
    if delay is None:
        delay = TIMING_CONFIG.device.default_back_delay

    adb_prefix = _get_adb_prefix(device_id)

    subprocess.run(
        adb_prefix + ["shell", "input", "keyevent", "4"], capture_output=True
    )
    time.sleep(delay)


def home(device_id: str | None = None, delay: float | None = None) -> None:
    """
    Press the home button.

    Args:
        device_id: Optional ADB device ID.
        delay: Delay in seconds after pressing home. If None, uses configured default.
    """
    if delay is None:
        delay = TIMING_CONFIG.device.default_home_delay

    adb_prefix = _get_adb_prefix(device_id)

    subprocess.run(
        adb_prefix + ["shell", "input", "keyevent", "KEYCODE_HOME"], capture_output=True
    )
    time.sleep(delay)


def launch_app(
    app_name: str, device_id: str | None = None, delay: float | None = None
) -> bool:
    """
    Launch an app by name.

    Args:
        app_name: The app name (must be in APP_PACKAGES).
        device_id: Optional ADB device ID.
        delay: Delay in seconds after launching. If None, uses configured default.

    Returns:
        True if app was launched, False if app not found.
    """
    if delay is None:
        delay = TIMING_CONFIG.device.default_launch_delay

    if app_name not in APP_PACKAGES:
        return False

    adb_prefix = _get_adb_prefix(device_id)
    package = APP_PACKAGES[app_name]

    subprocess.run(
        adb_prefix
        + [
            "shell",
            "monkey",
            "-p",
            package,
            "-c",
            "android.intent.category.LAUNCHER",
            "1",
        ],
        capture_output=True,
    )
    time.sleep(delay)
    return True


def get_app_state(package: str | None = None, device_id: str | None = None) -> dict:
    """
    Get the foreground state of an app.

    If package is None, returns the state of the current foreground app.

    Args:
        package: Optional package name to check. If None, checks the current foreground app.
        device_id: Optional ADB device ID.

    Returns:
        Dict with package, activity, resumed, stopped, pid.
    """
    adb_prefix = _get_adb_prefix(device_id)

    # Get top activity info
    result = subprocess.run(
        adb_prefix + ["shell", "dumpsys", "activity", "top"],
        capture_output=True, text=True, encoding="utf-8", timeout=10,
    )
    output = result.stdout

    # Parse ACTIVITY lines for resumed/stopped state
    current_package = None
    current_activity = None
    resumed = False
    stopped = False

    for line in output.split("\n"):
        line = line.strip()
        if line.startswith("ACTIVITY"):
            # e.g. "ACTIVITY com.example.app/.MainActivity ..."
            parts = line.split()
            if len(parts) >= 2:
                component = parts[1]
                if "/" in component:
                    pkg, act = component.split("/", 1)
                    # If checking a specific package, skip non-matching entries
                    if package and pkg != package:
                        current_package = None
                        current_activity = None
                        continue
                    current_package = pkg
                    # Reset state for each new matching ACTIVITY block
                    resumed = False
                    stopped = False
                    if act.startswith("."):
                        current_activity = pkg + act
                    else:
                        current_activity = act
        if current_package:
            if "mResumed=true" in line:
                resumed = True
            if "mStopped=true" in line:
                stopped = True

    # If no package specified, use whatever we found on top
    if not current_package and not package:
        # Fallback: use get_current_app style parsing
        current_package = "unknown"
        current_activity = "unknown"

    target_package = current_package or package or "unknown"

    # Get PID
    pid = None
    try:
        pid_result = subprocess.run(
            adb_prefix + ["shell", "pidof", target_package],
            capture_output=True, text=True, encoding="utf-8", timeout=5,
        )
        pid_str = pid_result.stdout.strip()
        if pid_str:
            pid = int(pid_str.split()[0])
    except (ValueError, subprocess.TimeoutExpired):
        pass

    return {
        "package": target_package,
        "activity": current_activity or "unknown",
        "resumed": resumed,
        "stopped": stopped,
        "pid": pid,
    }


def wait_for_app(
    package: str,
    timeout: int = 30,
    target_state: str = "resumed",
    device_id: str | None = None,
) -> dict:
    """
    Wait for an app to reach the target state with polling.

    Args:
        package: Package name to wait for.
        timeout: Maximum wait time in seconds.
        target_state: Target state - "resumed" or "running".
        device_id: Optional ADB device ID.

    Returns:
        Dict with package, activity, wait_time_seconds, state.

    Raises:
        TimeoutError: If the app doesn't reach the target state within timeout.
    """
    poll_interval = 2
    start_time = time.time()

    while True:
        elapsed = time.time() - start_time
        if elapsed > timeout:
            raise TimeoutError(
                f"App {package} did not reach state '{target_state}' "
                f"within {timeout}s"
            )

        state = get_app_state(package=package, device_id=device_id)

        if target_state == "resumed" and state["resumed"]:
            return {
                "package": state["package"],
                "activity": state["activity"],
                "wait_time_seconds": round(time.time() - start_time, 1),
                "state": "resumed",
            }
        elif target_state == "running" and state["pid"] is not None:
            return {
                "package": state["package"],
                "activity": state["activity"],
                "wait_time_seconds": round(time.time() - start_time, 1),
                "state": "running",
            }

        time.sleep(poll_interval)


def check_screen_health(
    threshold: float = 0.95,
    device_id: str | None = None,
) -> dict:
    """
    Check if the screen is healthy (not all-black or all-white).

    Takes an internal screenshot and analyzes pixel distribution.

    Args:
        threshold: Ratio threshold for declaring all-black/all-white (0.0-1.0).
        device_id: Optional ADB device ID.

    Returns:
        Dict with screen_state, dominant_color, black_ratio, white_ratio, screenshot_path.
    """
    from io import BytesIO

    from PIL import Image

    from phone_cli.adb.screenshot import get_screenshot

    screenshot = get_screenshot(device_id=device_id)

    # Decode image
    import base64
    img_data = base64.b64decode(screenshot.base64_data)
    img = Image.open(BytesIO(img_data))

    # Sample pixels for efficiency (every 10th pixel)
    pixels = list(img.getdata())
    total = len(pixels)
    step = max(1, total // 10000)  # Sample ~10000 pixels
    sampled = pixels[::step]
    sample_count = len(sampled)

    black_count = 0
    white_count = 0
    r_sum, g_sum, b_sum = 0, 0, 0

    for pixel in sampled:
        r, g, b = pixel[0], pixel[1], pixel[2]
        r_sum += r
        g_sum += g
        b_sum += b
        if r + g + b < 30:
            black_count += 1
        if r + g + b > 750:
            white_count += 1

    black_ratio = round(black_count / sample_count, 3)
    white_ratio = round(white_count / sample_count, 3)
    dominant_color = [
        r_sum // sample_count,
        g_sum // sample_count,
        b_sum // sample_count,
    ]

    if black_ratio >= threshold:
        screen_state = "all_black"
    elif white_ratio >= threshold:
        screen_state = "all_white"
    else:
        screen_state = "normal"

    # Save screenshot to temp file
    import tempfile
    import uuid as _uuid
    screenshot_path = os.path.join(
        tempfile.gettempdir(), "phone-cli", "screenshots",
        f"check_{_uuid.uuid4().hex[:8]}.png",
    )
    os.makedirs(os.path.dirname(screenshot_path), exist_ok=True)
    with open(screenshot_path, "wb") as f:
        f.write(img_data)

    return {
        "screen_state": screen_state,
        "dominant_color": dominant_color,
        "black_ratio": black_ratio,
        "white_ratio": white_ratio,
        "screenshot_path": screenshot_path,
    }


def get_app_log(
    package: str | None = None,
    filter_type: str = "all",
    lines: int = 20,
    device_id: str | None = None,
) -> dict:
    """
    Get app logs via adb logcat.

    Args:
        package: Package name. If None, uses current foreground app.
        filter_type: "crash", "lifecycle", or "all".
        lines: Number of log lines to return.
        device_id: Optional ADB device ID.

    Returns:
        Dict with package, pid, filter, lines, has_crash.
    """
    adb_prefix = _get_adb_prefix(device_id)

    # Resolve package if not specified
    if not package:
        package = get_current_app(device_id=device_id)
        # Try to get the actual package name from APP_PACKAGES
        if package in APP_PACKAGES:
            package = APP_PACKAGES[package]

    # Get PID
    pid = None
    try:
        pid_result = subprocess.run(
            adb_prefix + ["shell", "pidof", package],
            capture_output=True, text=True, encoding="utf-8", timeout=5,
        )
        pid_str = pid_result.stdout.strip()
        if pid_str:
            pid = int(pid_str.split()[0])
    except (ValueError, subprocess.TimeoutExpired):
        pass

    # Build logcat command
    logcat_cmd = adb_prefix + ["logcat", "-d"]
    if pid:
        logcat_cmd += [f"--pid={pid}"]

    result = subprocess.run(
        logcat_cmd,
        capture_output=True, text=True, encoding="utf-8", timeout=15,
    )

    log_lines = result.stdout.split("\n") if result.stdout else []

    # Apply filter
    if filter_type == "crash":
        pattern = re.compile(r"crash|exception|fatal|ANR", re.IGNORECASE)
        log_lines = [l for l in log_lines if pattern.search(l)]
    elif filter_type == "lifecycle":
        pattern = re.compile(
            r"onCreate|onResume|onStop|onDestroy|onPause", re.IGNORECASE
        )
        log_lines = [l for l in log_lines if pattern.search(l)]

    # Take last N lines
    filtered = [l.rstrip() for l in log_lines[-lines:] if l.strip()]

    # Check for crash indicators
    has_crash = any(
        kw in "\n".join(filtered).lower()
        for kw in ["crash", "fatal exception", "anr"]
    )

    return {
        "package": package,
        "pid": pid,
        "filter": filter_type,
        "lines": filtered,
        "has_crash": has_crash,
    }


def install_apk(
    apk_path: str,
    launch: bool = False,
    device_id: str | None = None,
) -> dict:
    """
    Install an APK and optionally launch it.

    Args:
        apk_path: Path to the APK file.
        launch: Whether to launch the app after installation.
        device_id: Optional ADB device ID.

    Returns:
        Dict with apk_path, package, launcher_activity, installed, launched.

    Raises:
        FileNotFoundError: If the APK file doesn't exist.
        RuntimeError: If installation fails.
    """
    if not os.path.exists(apk_path):
        raise FileNotFoundError(f"APK not found: {apk_path}")

    adb_prefix = _get_adb_prefix(device_id)
    package_name = None
    launcher_activity = None

    # Try to extract package info with aapt2
    try:
        aapt_result = subprocess.run(
            ["aapt2", "dump", "badging", apk_path],
            capture_output=True, text=True, timeout=15,
        )
        if aapt_result.returncode == 0:
            for line in aapt_result.stdout.split("\n"):
                if line.startswith("package:"):
                    # package: name='com.example.app' versionCode='1' ...
                    match = re.search(r"name='([^']+)'", line)
                    if match:
                        package_name = match.group(1)
                if "launchable-activity:" in line:
                    match = re.search(r"name='([^']+)'", line)
                    if match:
                        launcher_activity = match.group(1)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        # aapt2 not available, will try alternative after install
        pass

    # Install APK
    install_result = subprocess.run(
        adb_prefix + ["install", "-r", apk_path],
        capture_output=True, text=True, timeout=120,
    )
    if install_result.returncode != 0:
        error_msg = install_result.stderr or install_result.stdout
        raise RuntimeError(f"Install failed: {error_msg.strip()}")

    installed = "Success" in (install_result.stdout + install_result.stderr)
    if not installed:
        raise RuntimeError(
            f"Install may have failed: {(install_result.stdout + install_result.stderr).strip()}"
        )

    # If aapt2 didn't work, try to get info post-install
    if package_name and not launcher_activity:
        try:
            resolve_result = subprocess.run(
                adb_prefix + [
                    "shell", "cmd", "package", "resolve-activity",
                    "--brief", package_name,
                ],
                capture_output=True, text=True, timeout=10,
            )
            # Output format: priority=0 preferredOrder=0 match=0x108000\ncom.example.app/.MainActivity
            for line in resolve_result.stdout.strip().split("\n"):
                if "/" in line and "=" not in line:
                    launcher_activity = line.strip()
                    break
        except subprocess.TimeoutExpired:
            pass

    # Launch if requested
    launched = False
    if launch and package_name and launcher_activity:
        activity_ref = launcher_activity
        if "/" not in activity_ref:
            activity_ref = f"{package_name}/{launcher_activity}"
        subprocess.run(
            adb_prefix + ["shell", "am", "start", "-n", activity_ref],
            capture_output=True, text=True, timeout=10,
        )
        launched = True

    return {
        "apk_path": apk_path,
        "package": package_name,
        "launcher_activity": launcher_activity,
        "installed": True,
        "launched": launched,
    }


def _get_adb_prefix(device_id: str | None) -> list:
    """Get ADB command prefix with optional device specifier."""
    if device_id:
        return ["adb", "-s", device_id]
    return ["adb"]


def _parse_wm_size(output: str) -> Tuple[int, int]:
    """Parse `adb shell wm size` output."""

    override_match = re.search(r"Override size:\s*(\d+)x(\d+)", output)
    if override_match:
        return int(override_match.group(1)), int(override_match.group(2))

    physical_match = re.search(r"Physical size:\s*(\d+)x(\d+)", output)
    if physical_match:
        return int(physical_match.group(1)), int(physical_match.group(2))

    raise RuntimeError(f"Failed to parse Android screen size from: {output.strip()}")


def _get_display_rotation(device_id: str | None = None, timeout: int = 5) -> int | None:
    """Best-effort parse of current Android display rotation."""

    adb_prefix = _get_adb_prefix(device_id)
    try:
        result = subprocess.run(
            adb_prefix + ["shell", "dumpsys", "input"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
        )
    except Exception:
        return None

    output = (result.stdout or "") + "\n" + (result.stderr or "")
    for pattern in (
        r"SurfaceOrientation:\s*(\d+)",
        r"surfaceOrientation=\s*(\d+)",
        r"orientation=(\d+)",
    ):
        match = re.search(pattern, output)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                return None
    return None
