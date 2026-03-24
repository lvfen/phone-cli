from unittest.mock import MagicMock, patch

from phone_cli.adb.device import _parse_wm_size, get_screen_size


def test_parse_wm_size_prefers_override_size():
    output = "Physical size: 1080x2400\nOverride size: 720x1600\n"
    assert _parse_wm_size(output) == (720, 1600)


def test_get_screen_size_swaps_dimensions_for_landscape_rotation():
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = [
            MagicMock(stdout="Physical size: 1080x2400\n", stderr="", returncode=0),
            MagicMock(stdout="SurfaceOrientation: 1\n", stderr="", returncode=0),
        ]
        assert get_screen_size(device_id="dev1") == (2400, 1080)
