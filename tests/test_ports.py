# tests/test_ports.py
import socket
from unittest.mock import patch

from phone_cli.config.ports import (
    PORT_RANGES,
    PortExhaustedError,
    is_port_available,
)


def test_port_ranges_defined():
    assert "wda" in PORT_RANGES
    assert "adb" in PORT_RANGES
    assert "hdc" in PORT_RANGES
    assert PORT_RANGES["wda"] == (8100, 8200)
    assert PORT_RANGES["adb"] == (5037, 5100)
    assert PORT_RANGES["hdc"] == (5100, 5200)


def test_is_port_available_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    assert is_port_available(port) is True


def test_is_port_available_occupied_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        assert is_port_available(port) is False
