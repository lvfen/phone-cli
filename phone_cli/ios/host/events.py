"""Host-side input injection interfaces for macOS-backed runtimes."""

from __future__ import annotations

import time


def _require_quartz():
    try:
        import Quartz
    except Exception as exc:
        raise RuntimeError(f"Host event injection is unavailable: {exc}") from exc
    return Quartz


def _post_mouse_event(event_type: int, x: int, y: int, *, click_state: int = 1) -> None:
    Quartz = _require_quartz()
    event = Quartz.CGEventCreateMouseEvent(
        None,
        event_type,
        (x, y),
        Quartz.kCGMouseButtonLeft,
    )
    Quartz.CGEventSetIntegerValueField(
        event,
        Quartz.kCGMouseEventClickState,
        click_state,
    )
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)


def _post_keyboard_text(text: str) -> None:
    Quartz = _require_quartz()
    down = Quartz.CGEventCreateKeyboardEvent(None, 0, True)
    Quartz.CGEventKeyboardSetUnicodeString(down, len(text), text)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)

    up = Quartz.CGEventCreateKeyboardEvent(None, 0, False)
    Quartz.CGEventKeyboardSetUnicodeString(up, len(text), text)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)


def click_point(x: int, y: int) -> None:
    """Inject a left click at the specified host coordinate."""

    Quartz = _require_quartz()
    _post_mouse_event(Quartz.kCGEventLeftMouseDown, x, y)
    _post_mouse_event(Quartz.kCGEventLeftMouseUp, x, y)


def double_click_point(x: int, y: int) -> None:
    """Inject a left-button double click at the specified host coordinate."""

    Quartz = _require_quartz()
    for click_state in (1, 2):
        _post_mouse_event(Quartz.kCGEventLeftMouseDown, x, y, click_state=click_state)
        _post_mouse_event(Quartz.kCGEventLeftMouseUp, x, y, click_state=click_state)
        time.sleep(0.05)


def long_press_point(x: int, y: int, duration_ms: int = 3000) -> None:
    """Inject a left-button press-and-hold gesture."""

    Quartz = _require_quartz()
    _post_mouse_event(Quartz.kCGEventLeftMouseDown, x, y)
    time.sleep(max(duration_ms, 1) / 1000.0)
    _post_mouse_event(Quartz.kCGEventLeftMouseUp, x, y)


def drag_between(
    start_x: int,
    start_y: int,
    end_x: int,
    end_y: int,
    duration_ms: int | None = None,
) -> None:
    """Inject a simple drag gesture from start to end."""

    Quartz = _require_quartz()
    steps = 12
    duration_s = max(duration_ms or 300, 1) / 1000.0
    pause = duration_s / steps

    _post_mouse_event(Quartz.kCGEventLeftMouseDown, start_x, start_y)
    for index in range(1, steps + 1):
        x = int(start_x + (end_x - start_x) * index / steps)
        y = int(start_y + (end_y - start_y) * index / steps)
        _post_mouse_event(Quartz.kCGEventLeftMouseDragged, x, y)
        time.sleep(pause)
    _post_mouse_event(Quartz.kCGEventLeftMouseUp, end_x, end_y)


def type_text(text: str) -> None:
    """Inject unicode text via Quartz keyboard events."""

    if not text:
        return
    _post_keyboard_text(text)
