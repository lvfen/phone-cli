import json
from phone_cli.daemon.protocol import parse_request, ok_response, error_response, Request

class TestParseRequest:
    def test_valid_request(self):
        raw = json.dumps({"cmd": "acquire", "args": {"device_type": "ios"}})
        req = parse_request(raw)
        assert req.cmd == "acquire"
        assert req.args == {"device_type": "ios"}

    def test_missing_cmd(self):
        raw = json.dumps({"args": {}})
        req = parse_request(raw)
        assert req is None

    def test_invalid_json(self):
        req = parse_request("not json")
        assert req is None

    def test_args_default_empty(self):
        raw = json.dumps({"cmd": "status"})
        req = parse_request(raw)
        assert req.args == {}

class TestResponses:
    def test_ok_response(self):
        resp = ok_response({"session_id": "abc"})
        parsed = json.loads(resp)
        assert parsed["ok"] is True
        assert parsed["session_id"] == "abc"

    def test_ok_response_empty(self):
        resp = ok_response()
        parsed = json.loads(resp)
        assert parsed["ok"] is True

    def test_error_response(self):
        resp = error_response("session_not_found", "Unknown session")
        parsed = json.loads(resp)
        assert parsed["ok"] is False
        assert parsed["error"] == "session_not_found"
        assert parsed["msg"] == "Unknown session"
