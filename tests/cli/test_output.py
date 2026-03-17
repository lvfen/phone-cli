import json
from phone_cli.cli.output import ok_response, error_response, ErrorCode


def test_ok_response_with_data():
    result = ok_response({"path": "/tmp/shot.png", "width": 720})
    parsed = json.loads(result)
    assert parsed["status"] == "ok"
    assert parsed["data"]["path"] == "/tmp/shot.png"
    assert parsed["data"]["width"] == 720


def test_ok_response_without_data():
    result = ok_response()
    parsed = json.loads(result)
    assert parsed["status"] == "ok"
    assert parsed["data"] is None


def test_error_response():
    result = error_response(ErrorCode.DEVICE_DISCONNECTED, "Device offline")
    parsed = json.loads(result)
    assert parsed["status"] == "error"
    assert parsed["error_code"] == "DEVICE_DISCONNECTED"
    assert parsed["error_msg"] == "Device offline"


def test_error_codes_exist():
    assert ErrorCode.DEVICE_DISCONNECTED == "DEVICE_DISCONNECTED"
    assert ErrorCode.DEVICE_LOCKED == "DEVICE_LOCKED"
    assert ErrorCode.APP_NOT_FOUND == "APP_NOT_FOUND"
    assert ErrorCode.SCREENSHOT_FAILED == "SCREENSHOT_FAILED"
    assert ErrorCode.COMMAND_TIMEOUT == "COMMAND_TIMEOUT"
    assert ErrorCode.DAEMON_NOT_RUNNING == "DAEMON_NOT_RUNNING"
    assert ErrorCode.PERMISSION_DENIED == "PERMISSION_DENIED"
    assert ErrorCode.QUEUE_FULL == "QUEUE_FULL"
    assert ErrorCode.UI_TREE_UNAVAILABLE == "UI_TREE_UNAVAILABLE"
    assert ErrorCode.UNKNOWN_COMMAND == "UNKNOWN_COMMAND"
    assert ErrorCode.COMMAND_FAILED == "COMMAND_FAILED"
