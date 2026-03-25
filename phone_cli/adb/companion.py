"""HTTP client for Android Companion accessibility service."""

import json
import urllib.request
import urllib.error
from typing import Any


class CompanionUnavailableError(Exception):
    """Raised when the companion service is not reachable."""


class CompanionClient:
    """HTTP client for the Android Companion app running on device.

    The companion app listens on localhost:17342 (port-forwarded via ADB)
    and provides rich UI tree data and semantic actions through its
    accessibility service.
    """

    DEFAULT_HOST = "127.0.0.1"
    DEFAULT_PORT = 17342
    DEFAULT_TIMEOUT = 3
    UI_TREE_TIMEOUT = 5

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
    ):
        self._host = host or self.DEFAULT_HOST
        self._port = port or self.DEFAULT_PORT
        self._base_url = f"http://{self._host}:{self._port}"

    # ── Low-level helpers ────────────────────────────────────────────

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Send an HTTP request and return parsed JSON response."""
        url = f"{self._base_url}{path}"
        timeout = timeout or self.DEFAULT_TIMEOUT

        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"} if data else {},
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            raise CompanionUnavailableError(
                f"Cannot reach companion at {url}: {e}"
            ) from e

    def _get(self, path: str, timeout: float | None = None) -> dict[str, Any]:
        return self._request("GET", path, timeout=timeout)

    def _post(
        self,
        path: str,
        body: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        return self._request("POST", path, body=body or {}, timeout=timeout)

    # ── Status ───────────────────────────────────────────────────────

    def get_status(self) -> dict[str, Any]:
        """GET /status — returns ready/serviceConnected/packageName."""
        return self._get("/status")

    def is_ready(self) -> bool:
        """Quick check whether the companion service is ready."""
        try:
            status = self.get_status()
            return bool(status.get("ready"))
        except CompanionUnavailableError:
            return False

    # ── UI Tree ──────────────────────────────────────────────────────

    def get_ui_tree(self) -> dict[str, Any]:
        """POST /ui/tree — full UI snapshot with hierarchical node tree."""
        return self._post("/ui/tree", timeout=self.UI_TREE_TIMEOUT)

    # ── Node search ──────────────────────────────────────────────────

    def find_nodes(
        self,
        text: str | None = None,
        text_contains: str | None = None,
        resource_id: str | None = None,
        class_name: str | None = None,
        package_name: str | None = None,
        clickable: bool | None = None,
    ) -> dict[str, Any]:
        """POST /nodes/search — search UI nodes by criteria."""
        query: dict[str, Any] = {}
        if text is not None:
            query["text"] = text
        if text_contains is not None:
            query["textContains"] = text_contains
        if resource_id is not None:
            query["resourceId"] = resource_id
        if class_name is not None:
            query["className"] = class_name
        if package_name is not None:
            query["packageName"] = package_name
        if clickable is not None:
            query["clickable"] = clickable
        return self._post("/nodes/search", body=query)

    # ── Actions ──────────────────────────────────────────────────────

    def click_node(
        self,
        node_id: str,
        fallback_x: int | None = None,
        fallback_y: int | None = None,
    ) -> dict[str, Any]:
        """POST /actions/click-node — semantic click by nodeId."""
        body: dict[str, Any] = {"nodeId": node_id}
        if fallback_x is not None and fallback_y is not None:
            body["fallbackBounds"] = {
                "centerX": fallback_x,
                "centerY": fallback_y,
            }
        return self._post("/actions/click-node", body=body)

    def set_text(
        self,
        text: str,
        node_id: str | None = None,
    ) -> dict[str, Any]:
        """POST /actions/set-text — set text on a node or focused input."""
        body: dict[str, Any] = {"text": text}
        if node_id is not None:
            body["nodeId"] = node_id
        return self._post("/actions/set-text", body=body)

    def tap(self, x: int, y: int) -> dict[str, Any]:
        """POST /actions/tap — accessibility gesture tap."""
        return self._post("/actions/tap", body={"x": x, "y": y})

    def swipe(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        duration_ms: int = 250,
    ) -> dict[str, Any]:
        """POST /actions/swipe — accessibility gesture swipe."""
        return self._post(
            "/actions/swipe",
            body={
                "startX": start_x,
                "startY": start_y,
                "endX": end_x,
                "endY": end_y,
                "durationMs": duration_ms,
            },
        )

    # ── Screen context ───────────────────────────────────────────────

    def get_screen_context(self) -> dict[str, Any]:
        """GET /screen/context — interactive elements summary."""
        return self._get("/screen/context")
