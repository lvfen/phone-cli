"""Window screenshot interfaces shared by macOS-backed iOS runtimes."""

from __future__ import annotations

from dataclasses import dataclass

from phone_cli.ios.host.windows import HostWindow


@dataclass(frozen=True)
class WindowScreenshot:
    """Raw screenshot bytes captured from a host window."""

    window_id: int | str
    png_bytes: bytes


def capture_window(window: HostWindow) -> WindowScreenshot:
    """Capture a visible host window as PNG bytes."""

    try:
        import Quartz
        from AppKit import NSBitmapImageRep, NSPNGFileType
    except Exception as exc:
        raise RuntimeError(f"Window screenshot capture is unavailable: {exc}") from exc

    image_ref = Quartz.CGWindowListCreateImage(
        Quartz.CGRectNull,
        Quartz.kCGWindowListOptionIncludingWindow,
        int(window.window_id),
        Quartz.kCGWindowImageBoundsIgnoreFraming,
    )
    if image_ref is None:
        raise RuntimeError(f"Failed to capture window image for window {window.window_id}")

    bitmap = NSBitmapImageRep.alloc().initWithCGImage_(image_ref)
    data = bitmap.representationUsingType_properties_(NSPNGFileType, None)
    if data is None:
        raise RuntimeError(f"Failed to encode window screenshot for window {window.window_id}")

    return WindowScreenshot(
        window_id=window.window_id,
        png_bytes=bytes(data),
    )
