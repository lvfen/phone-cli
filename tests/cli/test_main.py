import json

from click.testing import CliRunner
from unittest.mock import patch

from phone_cli.cli.main import cli
from phone_cli.ios.runtime.discovery import RuntimeCandidate, RuntimeDiscoveryResult


def test_cli_version():
    runner = CliRunner()
    result = runner.invoke(cli, ["version"])
    assert result.exit_code == 0
    assert "phone-cli" in result.output


def test_cli_status_when_not_running():
    runner = CliRunner()
    with patch("phone_cli.cli.main.PhoneCLIDaemon") as mock_daemon_cls:
        mock_daemon_cls.return_value.status.return_value = {"status": "stopped"}
        result = runner.invoke(cli, ["status"])
    assert result.exit_code == 0
    assert "stopped" in result.output


def test_cli_detect_runtimes_command():
    runner = CliRunner()
    discovery = RuntimeDiscoveryResult(
        candidates=[
            RuntimeCandidate(runtime="device", target_id="dev1", label="iPhone"),
        ],
        reasons=[],
    )
    with patch("phone_cli.ios.runtime.discovery.detect_ios_runtimes", return_value=discovery):
        result = runner.invoke(cli, ["detect-runtimes", "--device-type", "ios"])
    assert result.exit_code == 0
    assert "auto_selectable" in result.output


def test_cli_start_passes_runtime():
    runner = CliRunner()
    with patch("phone_cli.cli.main.PhoneCLIDaemon") as mock_daemon_cls:
        mock_start = mock_daemon_cls.return_value.start
        mock_start.return_value = {"status": "running", "device_type": "ios"}
        result = runner.invoke(
            cli,
            ["start", "--device-type", "ios", "--runtime", "simulator"],
        )
    assert result.exit_code == 0
    mock_start.assert_called_once_with(
        device_type="ios",
        device_id=None,
        ios_runtime="simulator",
        foreground=False,
    )


def test_cli_devices_uses_selected_instance():
    runner = CliRunner()
    with patch("phone_cli.cli.main.PhoneCLIDaemon") as mock_daemon_cls:
        daemon = mock_daemon_cls.return_value
        daemon.send_command.return_value = json.dumps(
            {"status": "ok", "data": {"devices": []}}
        )
        result = runner.invoke(cli, ["--instance", "ios", "devices"])
    assert result.exit_code == 0
    mock_daemon_cls.assert_called_with(instance_name="ios")
    daemon.send_command.assert_called_once_with("devices")


def test_cli_companion_preflight_command():
    runner = CliRunner()
    with patch("phone_cli.cli.main.PhoneCLIDaemon") as mock_daemon_cls:
        daemon = mock_daemon_cls.return_value
        daemon.send_command.return_value = json.dumps(
            {"status": "ok", "data": {"ready": False, "issues": ["辅助服务已被系统标记为 crashed"]}}
        )
        result = runner.invoke(cli, ["companion-preflight"])
    assert result.exit_code == 0
    daemon.send_command.assert_called_once_with("companion_preflight")


def test_cli_search_click_command():
    runner = CliRunner()
    with patch("phone_cli.cli.main.PhoneCLIDaemon") as mock_daemon_cls:
        daemon = mock_daemon_cls.return_value
        daemon.send_command.return_value = json.dumps(
            {"status": "ok", "data": {"success": True, "action": "search_click"}}
        )
        result = runner.invoke(cli, ["search-click", "--text-contains", "动态", "--clickable"])
    assert result.exit_code == 0
    daemon.send_command.assert_called_once_with(
        "search_click",
        {"index": 0, "text_contains": "动态", "clickable": True},
    )


def test_cli_search_set_text_command():
    runner = CliRunner()
    with patch("phone_cli.cli.main.PhoneCLIDaemon") as mock_daemon_cls:
        daemon = mock_daemon_cls.return_value
        daemon.send_command.return_value = json.dumps(
            {"status": "ok", "data": {"success": True, "action": "search_set_text"}}
        )
        result = runner.invoke(
            cli,
            ["search-set-text", "hello", "--class-name", "android.widget.EditText"],
        )
    assert result.exit_code == 0
    daemon.send_command.assert_called_once_with(
        "search_set_text",
        {
            "text": "hello",
            "index": 0,
            "use_focused_fallback": True,
            "class_name": "android.widget.EditText",
        },
    )


def test_cli_stop_all_passes_flag():
    runner = CliRunner()
    with patch("phone_cli.cli.main.PhoneCLIDaemon") as mock_daemon_cls:
        daemon = mock_daemon_cls.return_value
        daemon.stop.return_value = {
            "status": "stopped",
            "stopped_instances": ["adb", "ios"],
        }
        result = runner.invoke(cli, ["stop", "--all"])
    assert result.exit_code == 0
    daemon.stop.assert_called_once_with(all_instances=True)


def test_cli_start_rejects_mismatched_instance():
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["--instance", "ios", "start", "--device-type", "adb"],
    )
    assert result.exit_code != 0
    assert "--instance must match start --device-type" in result.output


def test_cli_launch_passes_android_package_and_activity():
    runner = CliRunner()
    with patch("phone_cli.cli.main.PhoneCLIDaemon") as mock_daemon_cls:
        daemon = mock_daemon_cls.return_value
        daemon.send_command.return_value = json.dumps(
            {"status": "ok", "data": {"package_name": "com.example.app"}}
        )
        result = runner.invoke(
            cli,
            [
                "launch",
                "--package",
                "com.example.app",
                "--activity",
                "com.example.app.MainActivity",
            ],
        )
    assert result.exit_code == 0
    daemon.send_command.assert_called_once_with(
        "launch",
        {
            "app_name": None,
            "bundle_id": None,
            "app_path": None,
            "package_name": "com.example.app",
            "activity_name": "com.example.app.MainActivity",
        },
    )
