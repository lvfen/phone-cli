"""AI 会话轻量客户端，通过 Unix socket 与守护进程通信。"""
import json
import os
import socket


class PhoneClient:
    """AI 会话通过此客户端与守护进程通信。"""

    def __init__(self, socket_path: str = "~/.phone-cli/phone-cli.sock", timeout: float = 15.0) -> None:
        self._socket_path = os.path.expanduser(socket_path)
        self._timeout = timeout
        self._session_id: str | None = None

    def acquire(self, device_type: str, timeout: float = 300, wait: bool = True) -> dict:
        resp = self._send("acquire", device_type=device_type, timeout=timeout)
        if resp.get("ok") and resp.get("session_id"):
            self._session_id = resp["session_id"]
        return resp

    def release(self) -> dict:
        resp = self._send("release", session_id=self._session_id)
        self._session_id = None
        return resp

    def heartbeat(self) -> dict:
        return self._send("heartbeat", session_id=self._session_id)

    def status(self) -> dict:
        return self._send("status")

    def list_devices(self, device_type: str) -> dict:
        return self._send("list_devices", device_type=device_type)

    def operate(self, action: str, **kwargs) -> dict:
        return self._send("operate", session_id=self._session_id, action=action, **kwargs)

    def tap(self, x: int, y: int) -> dict:
        return self.operate("tap", x=x, y=y)

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration: int = 300) -> dict:
        return self.operate("swipe", x1=x1, y1=y1, x2=x2, y2=y2, duration=duration)

    def screenshot(self, path: str | None = None) -> dict:
        return self.operate("screenshot", path=path)

    @property
    def session_id(self) -> str | None:
        return self._session_id

    def _send(self, cmd: str, **args) -> dict:
        payload = json.dumps({"cmd": cmd, "args": args})
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self._timeout)
        try:
            sock.connect(self._socket_path)
            sock.sendall(payload.encode("utf-8"))
            sock.shutdown(socket.SHUT_WR)
            chunks: list[bytes] = []
            while True:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)
            return json.loads(b"".join(chunks).decode("utf-8"))
        except ConnectionRefusedError:
            return {"ok": False, "error": "daemon_not_running", "msg": "Cannot connect to daemon"}
        except socket.timeout:
            return {"ok": False, "error": "timeout", "msg": "Request timed out"}
        finally:
            sock.close()
