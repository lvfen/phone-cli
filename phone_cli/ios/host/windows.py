"""Window abstractions shared by simulator and app_on_mac runtimes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

SIMULATOR_BUNDLE_ID = "com.apple.iphonesimulator"


@dataclass(frozen=True)
class Rect:
    """A screen-space rectangle in pixels."""

    x: int
    y: int
    width: int
    height: int

    def to_dict(self) -> dict[str, int]:
        return {
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
        }


@dataclass(frozen=True)
class HostWindow:
    """A host window that may back a simulator or app_on_mac target."""

    window_id: int | str
    owner_name: str
    bundle_id: str | None
    title: str
    bounds: Rect
    render_bounds: Rect | None = None
    pid: int | None = None

    def target_bounds(self) -> Rect:
        return self.render_bounds or self.bounds

    def to_dict(self) -> dict[str, object]:
        return {
            "window_id": self.window_id,
            "owner_name": self.owner_name,
            "bundle_id": self.bundle_id,
            "title": self.title,
            "bounds": self.bounds.to_dict(),
            "render_bounds": self.render_bounds.to_dict() if self.render_bounds else None,
            "pid": self.pid,
        }


def map_relative_point(rect: Rect, rx: int, ry: int) -> tuple[int, int]:
    """Map a 0-999 point onto the supplied rectangle."""

    clamped_x = max(0, min(999, rx))
    clamped_y = max(0, min(999, ry))
    x = rect.x + int(clamped_x / 999 * rect.width)
    y = rect.y + int(clamped_y / 999 * rect.height)
    return min(x, rect.x + rect.width - 1), min(y, rect.y + rect.height - 1)


def map_device_point(window: HostWindow, device_size: tuple[int, int], x: int, y: int) -> tuple[int, int]:
    """Map a simulator/app display point to the host window's render region."""

    render_rect = window.target_bounds()
    device_width = max(device_size[0], 1)
    device_height = max(device_size[1], 1)
    clamped_x = max(0, min(device_width - 1, x))
    clamped_y = max(0, min(device_height - 1, y))
    mapped_x = render_rect.x + int(clamped_x / max(device_width - 1, 1) * render_rect.width)
    mapped_y = render_rect.y + int(clamped_y / max(device_height - 1, 1) * render_rect.height)
    return (
        min(mapped_x, render_rect.x + render_rect.width - 1),
        min(mapped_y, render_rect.y + render_rect.height - 1),
    )


def list_windows(
    bundle_id: str | None = None,
    owner_name: str | None = None,
    title_contains: str | None = None,
) -> list[HostWindow]:
    """Enumerate visible host windows, optionally filtered by owner or title."""

    try:
        import Quartz
        from AppKit import NSRunningApplication
    except Exception as exc:
        raise RuntimeError(f"Host window enumeration is unavailable: {exc}") from exc

    window_infos = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionOnScreenOnly,
        Quartz.kCGNullWindowID,
    )
    windows: list[HostWindow] = []
    for info in window_infos or []:
        if int(info.get("kCGWindowLayer", 0)) != 0:
            continue

        bounds_dict = info.get("kCGWindowBounds") or {}
        width = int(bounds_dict.get("Width", 0))
        height = int(bounds_dict.get("Height", 0))
        if width <= 0 or height <= 0:
            continue

        window_id = info.get("kCGWindowNumber")
        pid = int(info.get("kCGWindowOwnerPID", 0))
        owner = info.get("kCGWindowOwnerName", "") or ""
        title = info.get("kCGWindowName", "") or ""

        app_bundle_id = None
        if pid:
            app = NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
            if app is not None:
                app_bundle_id = app.bundleIdentifier()

        if bundle_id and app_bundle_id != bundle_id:
            continue
        if owner_name and owner != owner_name:
            continue
        if title_contains and title_contains not in title:
            continue

        bounds = Rect(
            x=int(bounds_dict.get("X", 0)),
            y=int(bounds_dict.get("Y", 0)),
            width=width,
            height=height,
        )
        render_bounds = _estimate_render_bounds(
            owner_name=owner,
            bundle_id=app_bundle_id,
            bounds=bounds,
        )
        windows.append(
            HostWindow(
                window_id=window_id,
                owner_name=owner,
                bundle_id=app_bundle_id,
                title=title,
                bounds=bounds,
                render_bounds=render_bounds,
                pid=pid or None,
            )
        )
    return windows


def get_window(window_id: int | str) -> HostWindow:
    """Return a single window by ID."""

    for window in list_windows():
        if str(window.window_id) == str(window_id):
            return window
    raise RuntimeError(f"Window not found: {window_id}")


def find_simulator_window(device_name: str | None = None) -> HostWindow:
    """Find the best foreground Simulator window for the target device."""

    title_filters = [device_name] if device_name else [None]
    for title_filter in title_filters:
        windows = list_windows(
            bundle_id=SIMULATOR_BUNDLE_ID,
            title_contains=title_filter,
        )
        if windows:
            return _pick_frontmost_window(windows)
    windows = list_windows(bundle_id=SIMULATOR_BUNDLE_ID)
    if windows:
        return _pick_frontmost_window(windows)
    raise RuntimeError("No visible Simulator window was found.")


def find_app_window(
    bundle_id: str | None = None,
    owner_name: str | None = None,
    title_contains: str | None = None,
) -> HostWindow:
    """Find the best visible window for an app_on_mac target."""

    windows = list_windows(
        bundle_id=bundle_id,
        owner_name=owner_name,
        title_contains=title_contains,
    )
    if not windows:
        raise RuntimeError("No visible application window was found.")
    return _pick_frontmost_window(windows)


def _estimate_render_bounds(
    owner_name: str,
    bundle_id: str | None,
    bounds: Rect,
) -> Rect:
    """Best-effort render-area estimate for host-driven runtimes."""

    if bundle_id == SIMULATOR_BUNDLE_ID or owner_name == "Simulator":
        # Simulator windows include a title bar and a small chrome inset.
        inset_x = 8
        top_inset = 56
        bottom_inset = 8
        width = max(1, bounds.width - inset_x * 2)
        height = max(1, bounds.height - top_inset - bottom_inset)
        return Rect(
            x=bounds.x + inset_x,
            y=bounds.y + top_inset,
            width=width,
            height=height,
        )
    return bounds


def _pick_frontmost_window(windows: Iterable[HostWindow]) -> HostWindow:
    """Pick the first visible window from the front-to-back system order."""

    ordered = list(windows)
    if not ordered:
        raise RuntimeError("No visible host window was found.")
    return ordered[0]
