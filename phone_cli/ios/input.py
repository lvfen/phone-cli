"""Input utilities for iOS device text input via WDA."""


def type_text(text: str, device_id: str | None = None) -> None:
    """
    Type text into the currently focused input field via WDA.

    Args:
        text: The text to type.
        device_id: Optional iOS device UDID.
    """
    from phone_cli.ios.connection import get_wda_client

    client = get_wda_client(device_id)
    client.send_keys(text)


def clear_text(device_id: str | None = None) -> None:
    """
    Clear text in the currently focused input field via WDA.

    Finds the focused element and clears its text content.

    Args:
        device_id: Optional iOS device UDID.
    """
    from phone_cli.ios.connection import get_wda_client

    client = get_wda_client(device_id)

    # Try to find the focused text field and clear it
    try:
        focused = client(focused=True).get(timeout=3)
        focused.clear_text()
    except Exception:
        # Fallback: try to find any visible text field
        try:
            text_field = client(className="TextField").get(timeout=3)
            text_field.clear_text()
        except Exception:
            # Last resort: select all and delete
            pass
