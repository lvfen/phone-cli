"""Screenshot utilities for capturing iOS device screen via WDA."""

import base64
from dataclasses import dataclass
from io import BytesIO

from PIL import Image


@dataclass
class Screenshot:
    """Represents a captured screenshot."""

    base64_data: str
    width: int
    height: int
    is_sensitive: bool = False


def get_screenshot(device_id: str | None = None, timeout: int = 10) -> Screenshot:
    """
    Capture a screenshot from the connected iOS device via WDA.

    Args:
        device_id: Optional iOS device UDID.
        timeout: Timeout in seconds (used for connection).

    Returns:
        Screenshot object containing base64 data and dimensions.

    Note:
        If the screenshot fails, a black fallback image is returned
        with iPhone 13/14 logical resolution (1170x2532).
    """
    try:
        from phone_cli.ios.connection import get_wda_client

        client = get_wda_client(device_id)
        pil_img = client.screenshot()

        if not isinstance(pil_img, Image.Image):
            # Some versions return bytes
            pil_img = Image.open(BytesIO(pil_img))

        width, height = pil_img.size

        buffered = BytesIO()
        pil_img.save(buffered, format="PNG")
        base64_data = base64.b64encode(buffered.getvalue()).decode("utf-8")

        return Screenshot(
            base64_data=base64_data,
            width=width,
            height=height,
            is_sensitive=False,
        )

    except Exception as e:
        print(f"iOS screenshot error: {e}")
        return _create_fallback_screenshot()


def _create_fallback_screenshot(is_sensitive: bool = False) -> Screenshot:
    """Create a black fallback image when screenshot fails."""
    # iPhone 13/14 logical resolution
    default_width, default_height = 1170, 2532

    black_img = Image.new("RGB", (default_width, default_height), color="black")
    buffered = BytesIO()
    black_img.save(buffered, format="PNG")
    base64_data = base64.b64encode(buffered.getvalue()).decode("utf-8")

    return Screenshot(
        base64_data=base64_data,
        width=default_width,
        height=default_height,
        is_sensitive=is_sensitive,
    )
