"""IPC 协议定义：请求解析、响应构建。"""
import json
from dataclasses import dataclass


@dataclass
class Request:
    cmd: str
    args: dict


def parse_request(raw: str) -> Request | None:
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    cmd = data.get("cmd")
    if not cmd:
        return None
    return Request(cmd=cmd, args=data.get("args", {}))


def ok_response(data: dict | None = None) -> str:
    resp = {"ok": True}
    if data:
        resp.update(data)
    return json.dumps(resp, ensure_ascii=False)


def error_response(error: str, msg: str) -> str:
    return json.dumps({"ok": False, "error": error, "msg": msg}, ensure_ascii=False)
