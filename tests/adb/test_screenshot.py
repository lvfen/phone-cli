from io import BytesIO
from unittest.mock import MagicMock, patch

from PIL import Image

from phone_cli.adb.screenshot import get_screenshot


def _png_bytes(width: int = 3, height: int = 2) -> bytes:
    image = Image.new("RGB", (width, height), color="white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_get_screenshot_prefers_exec_out_fast_path():
    png_bytes = _png_bytes()
    with patch("phone_cli.adb.screenshot.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=png_bytes, stderr=b"", returncode=0)
        screenshot = get_screenshot(device_id="dev1")

    assert screenshot.width == 3
    assert screenshot.height == 2
    assert screenshot.is_sensitive is False
    assert mock_run.call_args_list[0].args[0] == [
        "adb",
        "-s",
        "dev1",
        "exec-out",
        "screencap",
        "-p",
    ]
