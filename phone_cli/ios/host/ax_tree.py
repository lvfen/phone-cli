"""Accessibility tree abstractions for app_on_mac automation."""

from __future__ import annotations

from dataclasses import dataclass, field

from phone_cli.ios.host.windows import get_window


@dataclass(frozen=True)
class AXNode:
    """A normalized accessibility node."""

    role: str
    title: str | None = None
    description: str | None = None
    value: str | None = None
    x: int | None = None
    y: int | None = None
    width: int | None = None
    height: int | None = None
    enabled: bool | None = None
    focused: bool | None = None
    children: list["AXNode"] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "role": self.role,
            "title": self.title,
            "description": self.description,
            "value": self.value,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "enabled": self.enabled,
            "focused": self.focused,
            "children": [child.to_dict() for child in self.children],
        }


def read_window_tree(window_id: int | str) -> AXNode:
    """Read a macOS accessibility tree for the supplied window."""

    window = get_window(window_id)
    fallback = AXNode(
        role="Window",
        title=window.title or None,
        x=window.target_bounds().x,
        y=window.target_bounds().y,
        width=window.target_bounds().width,
        height=window.target_bounds().height,
        enabled=True,
        focused=True,
    )

    try:
        import ApplicationServices as AS
    except Exception:
        return fallback

    if not window.pid:
        return fallback

    try:
        app_ref = AS.AXUIElementCreateApplication(window.pid)
        ax_windows = _copy_attribute(AS, app_ref, "AXWindows") or []
        target_window = _match_window_element(AS, ax_windows, window.title)
        if target_window is None:
            target_window = _copy_attribute(AS, app_ref, "AXFocusedWindow")
        if target_window is None:
            return fallback
        ax_root = _read_node(AS, target_window, depth=0, max_depth=4)
        return _merge_window_geometry(ax_root, window)
    except Exception:
        return fallback


def flatten_tree(root: AXNode) -> list[dict[str, object]]:
    """Flatten an AX tree into a list of dictionaries."""

    elements: list[dict[str, object]] = []

    def _walk(node: AXNode) -> None:
        elements.append(node.to_dict())
        for child in node.children:
            _walk(child)

    _walk(root)
    return elements


def _copy_attribute(as_module, element, attribute: str):
    """Safely copy an accessibility attribute from an element."""

    result = as_module.AXUIElementCopyAttributeValue(element, attribute, None)
    if isinstance(result, tuple):
        if len(result) == 2:
            error, value = result
            if error not in (0, getattr(as_module, "kAXErrorSuccess", 0)):
                return None
            return value
        return result[-1]
    return result


def _match_window_element(as_module, ax_windows, title: str) -> object | None:
    """Pick the AX window element that best matches the host window title."""

    if not ax_windows:
        return None
    if not title:
        return ax_windows[0]
    for ax_window in ax_windows:
        ax_title = _copy_attribute(as_module, ax_window, "AXTitle")
        if ax_title == title:
            return ax_window
    return ax_windows[0]


def _read_node(as_module, element, *, depth: int, max_depth: int) -> AXNode:
    """Read one AX element into the normalized node model."""

    role = _coerce_text(_copy_attribute(as_module, element, "AXRole")) or "AXElement"
    title = _coerce_text(_copy_attribute(as_module, element, "AXTitle"))
    description = _coerce_text(_copy_attribute(as_module, element, "AXDescription"))
    value = _coerce_text(_copy_attribute(as_module, element, "AXValue"))
    enabled = _coerce_bool(_copy_attribute(as_module, element, "AXEnabled"))
    focused = _coerce_bool(_copy_attribute(as_module, element, "AXFocused"))
    position = _copy_attribute(as_module, element, "AXPosition")
    size = _copy_attribute(as_module, element, "AXSize")

    x, y = _coerce_point(position)
    width, height = _coerce_size(size)
    children: list[AXNode] = []
    if depth < max_depth:
        raw_children = _copy_attribute(as_module, element, "AXChildren") or []
        for child in raw_children:
            try:
                children.append(_read_node(as_module, child, depth=depth + 1, max_depth=max_depth))
            except Exception:
                continue

    return AXNode(
        role=role,
        title=title,
        description=description,
        value=value,
        x=x,
        y=y,
        width=width,
        height=height,
        enabled=enabled,
        focused=focused,
        children=children,
    )


def _merge_window_geometry(root: AXNode, window) -> AXNode:
    """Fill missing root geometry from the host window model."""

    bounds = window.target_bounds()
    return AXNode(
        role=root.role,
        title=root.title or window.title or None,
        description=root.description,
        value=root.value,
        x=root.x if root.x is not None else bounds.x,
        y=root.y if root.y is not None else bounds.y,
        width=root.width if root.width is not None else bounds.width,
        height=root.height if root.height is not None else bounds.height,
        enabled=root.enabled,
        focused=root.focused,
        children=root.children,
    )


def _coerce_text(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="ignore")
    return str(value)


def _coerce_bool(value) -> bool | None:
    if value is None:
        return None
    return bool(value)


def _coerce_point(value) -> tuple[int | None, int | None]:
    if value is None:
        return None, None
    if isinstance(value, (tuple, list)) and len(value) >= 2:
        return int(value[0]), int(value[1])
    if hasattr(value, "x") and hasattr(value, "y"):
        return int(value.x), int(value.y)
    if hasattr(value, "pointValue"):
        point = value.pointValue()
        return int(point.x), int(point.y)
    return None, None


def _coerce_size(value) -> tuple[int | None, int | None]:
    if value is None:
        return None, None
    if isinstance(value, (tuple, list)) and len(value) >= 2:
        return int(value[0]), int(value[1])
    if hasattr(value, "width") and hasattr(value, "height"):
        return int(value.width), int(value.height)
    if hasattr(value, "sizeValue"):
        size = value.sizeValue()
        return int(size.width), int(size.height)
    return None, None
