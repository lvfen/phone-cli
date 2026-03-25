"""端口范围常量与端口可用性检测工具。"""

import socket

PORT_RANGES: dict[str, tuple[int, int]] = {
    "wda": (8100, 8200),
    "adb": (5037, 5100),
    "hdc": (5100, 5200),
}


class PortExhaustedError(Exception):
    """端口范围内所有端口均被占用。"""


def is_port_available(port: int) -> bool:
    """检测端口是否可用。使用 bind 检测。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False
