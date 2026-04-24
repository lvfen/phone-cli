import subprocess
from unittest.mock import MagicMock, patch

from phone_cli.adb.device import (
    _parse_wm_size,
    get_app_log,
    get_current_app,
    get_screen_size,
    launch_app,
)


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


def test_get_current_app_returns_unknown_package_instead_of_system_home():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            stdout="mCurrentFocus=Window{u0 com.example.app/com.example.app.MainActivity}\n",
            stderr="",
            returncode=0,
        )
        assert get_current_app(device_id="dev1") == "com.example.app"


def test_get_current_app_returns_system_home_on_timeout():
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="dumpsys", timeout=10)):
        assert get_current_app(device_id="dev1") == "System Home"


def test_launch_app_accepts_direct_package_name():
    with patch("subprocess.run") as mock_run, patch("time.sleep"):
        mock_run.side_effect = [
            MagicMock(stdout="", stderr="", returncode=1),
            MagicMock(stdout="", stderr="", returncode=0),
        ]
        success = launch_app("com.example.app", device_id="dev1")
    assert success is True
    assert mock_run.call_args_list[-1].args[0] == [
        "adb",
        "-s",
        "dev1",
        "shell",
        "monkey",
        "-p",
        "com.example.app",
        "-c",
        "android.intent.category.LAUNCHER",
        "1",
    ]


def test_launch_app_prefers_main_activity_over_leak_launcher():
    with patch("subprocess.run") as mock_run, patch("time.sleep"):
        mock_run.side_effect = [
            MagicMock(
                stdout=(
                    "com.example.app/leakcanary.internal.activity.LeakLauncherActivity\n"
                    "com.example.app/.MainActivity\n"
                ),
                stderr="",
                returncode=0,
            ),
            MagicMock(stdout="Starting: Intent { ... }", stderr="", returncode=0),
            MagicMock(
                stdout=(
                    "ACTIVITY com.example.app/.MainActivity 1234 pid=1234\n"
                    "  mResumed=true\n"
                ),
                stderr="",
                returncode=0,
            ),
            MagicMock(stdout="1234\n", stderr="", returncode=0),
        ]
        success = launch_app("com.example.app", device_id="dev1")
    assert success is True
    assert mock_run.call_args_list[1].kwargs["timeout"] == 10
    assert mock_run.call_args_list[1].args[0] == [
        "adb",
        "-s",
        "dev1",
        "shell",
        "am",
        "start",
        "-n",
        "com.example.app/.MainActivity",
    ]


def test_launch_app_retries_when_started_activity_redirects_to_auxiliary_entry():
    with patch("subprocess.run") as mock_run, patch("time.sleep"):
        mock_run.side_effect = [
            MagicMock(
                stdout=(
                    "com.example.app/.MainActivity\n"
                    "com.example.app/.HomeActivity\n"
                ),
                stderr="",
                returncode=0,
            ),
            MagicMock(stdout="Starting: Intent { ... }", stderr="", returncode=0),
            MagicMock(
                stdout=(
                    "ACTIVITY com.example.app/leakcanary.internal.activity.LeakLauncherActivity "
                    "1234 pid=1234\n"
                    "  mResumed=true\n"
                ),
                stderr="",
                returncode=0,
            ),
            MagicMock(stdout="1234\n", stderr="", returncode=0),
            MagicMock(stdout="Starting: Intent { ... }", stderr="", returncode=0),
            MagicMock(
                stdout=(
                    "ACTIVITY com.example.app/.HomeActivity 1234 pid=1234\n"
                    "  mResumed=true\n"
                ),
                stderr="",
                returncode=0,
            ),
            MagicMock(stdout="1234\n", stderr="", returncode=0),
        ]
        success = launch_app("com.example.app", device_id="dev1")
    assert success is True
    assert mock_run.call_args_list[4].args[0] == [
        "adb",
        "-s",
        "dev1",
        "shell",
        "am",
        "start",
        "-n",
        "com.example.app/.HomeActivity",
    ]


def test_launch_app_supports_detailed_query_activities_output():
    with patch("subprocess.run") as mock_run, patch("time.sleep"):
        mock_run.side_effect = [
            MagicMock(
                stdout=(
                    "3 activities found:\n"
                    "  Activity #0:\n"
                    "    ActivityInfo:\n"
                    "      name=com.example.app.WelcomeActivity\n"
                    "      packageName=com.example.app\n"
                    "    ApplicationInfo:\n"
                    "      name=com.example.app.Application\n"
                    "  Activity #1:\n"
                    "    ActivityInfo:\n"
                    "      name=leakcanary.internal.activity.LeakLauncherActivity\n"
                    "      packageName=com.example.app\n"
                ),
                stderr="",
                returncode=0,
            ),
            MagicMock(stdout="Starting: Intent { ... }", stderr="", returncode=0),
            MagicMock(
                stdout=(
                    "ACTIVITY com.example.app/.WelcomeActivity 1234 pid=1234\n"
                    "  mResumed=true\n"
                ),
                stderr="",
                returncode=0,
            ),
            MagicMock(stdout="1234\n", stderr="", returncode=0),
        ]
        success = launch_app("com.example.app", device_id="dev1")
    assert success is True
    assert mock_run.call_args_list[1].args[0] == [
        "adb",
        "-s",
        "dev1",
        "shell",
        "am",
        "start",
        "-n",
        "com.example.app/com.example.app.WelcomeActivity",
    ]


def test_launch_app_prefers_explicit_activity_over_monkey():
    with patch("subprocess.run") as mock_run, patch("time.sleep"):
        success = launch_app(
            "com.example.app",
            device_id="dev1",
            activity_name="com.example.app.MainActivity",
        )
    assert success is True
    mock_run.assert_called_once_with(
        [
            "adb",
            "-s",
            "dev1",
            "shell",
            "am",
            "start",
            "-n",
            "com.example.app/com.example.app.MainActivity",
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )


def test_get_app_log_tolerates_non_utf8_output():
    def fake_run(*args, **kwargs):
        if args[0][-2:] == ["shell", "pidof"] or (
            len(args[0]) >= 4 and args[0][2:4] == ["shell", "pidof"]
        ):
            return MagicMock(stdout="1234\n", stderr="", returncode=0)
        return MagicMock(stdout=b"bad\xe7line\n", stderr=b"", returncode=0)

    with patch("subprocess.run", side_effect=fake_run):
        result = get_app_log(package="com.example.app", device_id="dev1")
    assert result["package"] == "com.example.app"
    assert result["lines"] == ["bad�line"]
    assert result["has_crash"] is False
