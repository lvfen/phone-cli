"""Tests for Android Companion integration."""

import json
from unittest.mock import MagicMock, patch, PropertyMock

from phone_cli.cli.commands import dispatch_command
from phone_cli.cli.output import ErrorCode


# ── CompanionClient tests ────────────────────────────────────────────

class TestCompanionClient:
    """Tests for the CompanionClient HTTP client."""

    @staticmethod
    def _reset_ready_cache() -> None:
        from phone_cli.adb.companion import CompanionClient

        CompanionClient._ready_cache.clear()

    def test_is_ready_returns_true_when_service_ready(self):
        from phone_cli.adb.companion import CompanionClient

        self._reset_ready_cache()
        with patch.object(CompanionClient, "get_status", return_value={"ready": True}):
            client = CompanionClient()
            assert client.is_ready() is True

    def test_is_ready_returns_false_when_service_not_ready(self):
        from phone_cli.adb.companion import CompanionClient

        self._reset_ready_cache()
        with patch.object(
            CompanionClient, "get_status", return_value={"ready": False}
        ):
            client = CompanionClient()
            assert client.is_ready() is False

    def test_is_ready_returns_false_on_connection_error(self):
        from phone_cli.adb.companion import (
            CompanionClient,
            CompanionUnavailableError,
        )

        self._reset_ready_cache()
        with patch.object(
            CompanionClient,
            "get_status",
            side_effect=CompanionUnavailableError("connection refused"),
        ):
            client = CompanionClient()
            assert client.is_ready() is False

    def test_is_ready_uses_short_ttl_cache(self):
        from phone_cli.adb.companion import CompanionClient

        self._reset_ready_cache()
        with patch.object(CompanionClient, "get_status", return_value={"ready": True}) as mock_status, \
             patch("phone_cli.adb.companion.time.monotonic", side_effect=[10.0, 10.2]):
            first_client = CompanionClient()
            second_client = CompanionClient()
            assert first_client.is_ready() is True
            assert second_client.is_ready() is True
        assert mock_status.call_count == 1

    def test_is_ready_cache_is_scoped_per_endpoint(self):
        from phone_cli.adb.companion import CompanionClient

        self._reset_ready_cache()
        with patch.object(
            CompanionClient,
            "get_status",
            side_effect=[{"ready": True}, {"ready": False}],
        ) as mock_status, patch("phone_cli.adb.companion.time.monotonic", side_effect=[20.0, 20.1]):
            first_client = CompanionClient(host="127.0.0.1", port=17342)
            second_client = CompanionClient(host="127.0.0.1", port=17343)
            assert first_client.is_ready() is True
            assert second_client.is_ready() is False
        assert mock_status.call_count == 2

    def test_find_nodes_builds_correct_query(self):
        from phone_cli.adb.companion import CompanionClient

        with patch.object(
            CompanionClient,
            "_post",
            return_value={"totalMatches": 1, "nodes": [{"nodeId": "0.1"}]},
        ) as mock_post:
            client = CompanionClient()
            result = client.find_nodes(text="登录", clickable=True)
            mock_post.assert_called_once_with(
                "/nodes/search",
                body={"text": "登录", "clickable": True},
            )
            assert result["totalMatches"] == 1

    def test_click_node_with_fallback(self):
        from phone_cli.adb.companion import CompanionClient

        with patch.object(
            CompanionClient,
            "_post",
            return_value={"success": True, "source": "companion"},
        ) as mock_post:
            client = CompanionClient()
            result = client.click_node("0.3.1", fallback_x=200, fallback_y=300)
            mock_post.assert_called_once_with(
                "/actions/click-node",
                body={
                    "nodeId": "0.3.1",
                    "fallbackBounds": {"centerX": 200, "centerY": 300},
                },
            )
            assert result["success"] is True

    def test_set_text_with_node_id(self):
        from phone_cli.adb.companion import CompanionClient

        with patch.object(
            CompanionClient,
            "_post",
            return_value={"success": True},
        ) as mock_post:
            client = CompanionClient()
            result = client.set_text("hello", node_id="0.2.1")
            mock_post.assert_called_once_with(
                "/actions/set-text",
                body={"text": "hello", "nodeId": "0.2.1"},
            )
            assert result["success"] is True

    def test_set_text_without_node_id(self):
        from phone_cli.adb.companion import CompanionClient

        with patch.object(
            CompanionClient,
            "_post",
            return_value={"success": True},
        ) as mock_post:
            client = CompanionClient()
            result = client.set_text("hello")
            mock_post.assert_called_once_with(
                "/actions/set-text",
                body={"text": "hello"},
            )

    def test_search_and_click_builds_correct_query(self):
        from phone_cli.adb.companion import CompanionClient

        with patch.object(
            CompanionClient,
            "_post",
            return_value={"success": True, "action": "search_click"},
        ) as mock_post:
            client = CompanionClient()
            result = client.search_and_click(text_contains="动态", clickable=True, index=1)
            mock_post.assert_called_once_with(
                "/actions/search-click",
                body={"index": 1, "textContains": "动态", "clickable": True},
            )
            assert result["success"] is True

    def test_search_and_set_text_builds_correct_query(self):
        from phone_cli.adb.companion import CompanionClient

        with patch.object(
            CompanionClient,
            "_post",
            return_value={"success": True, "action": "search_set_text"},
        ) as mock_post:
            client = CompanionClient()
            result = client.search_and_set_text(
                text="hello",
                match_text="请输入",
                class_name="android.widget.EditText",
                use_focused_fallback=False,
            )
            mock_post.assert_called_once_with(
                "/actions/search-set-text",
                body={
                    "text": "hello",
                    "index": 0,
                    "useFocusedFallback": False,
                    "matchText": "请输入",
                    "className": "android.widget.EditText",
                },
            )
            assert result["success"] is True

    def test_tap(self):
        from phone_cli.adb.companion import CompanionClient

        with patch.object(
            CompanionClient,
            "_post",
            return_value={"success": True, "source": "companion"},
        ) as mock_post:
            client = CompanionClient()
            result = client.tap(100, 200)
            mock_post.assert_called_once_with(
                "/actions/tap",
                body={"x": 100, "y": 200},
                timeout=8,
            )

    def test_swipe(self):
        from phone_cli.adb.companion import CompanionClient

        with patch.object(
            CompanionClient,
            "_post",
            return_value={"success": True, "source": "companion"},
        ) as mock_post:
            client = CompanionClient()
            result = client.swipe(100, 200, 300, 400, duration_ms=500)
            mock_post.assert_called_once_with(
                "/actions/swipe",
                body={
                    "startX": 100,
                    "startY": 200,
                    "endX": 300,
                    "endY": 400,
                    "durationMs": 500,
                },
                timeout=3.5,
            )

    def test_get_screen_context(self):
        from phone_cli.adb.companion import CompanionClient

        context = {
            "packageName": "com.example",
            "clickableNodes": [{"text": "OK"}],
            "editableNodes": [],
        }
        with patch.object(
            CompanionClient, "_get", return_value=context
        ) as mock_get:
            client = CompanionClient()
            result = client.get_screen_context()
            mock_get.assert_called_once_with("/screen/context")
            assert result["packageName"] == "com.example"


# ── CompanionManager tests ───────────────────────────────────────────

class TestCompanionManager:
    """Tests for the CompanionManager lifecycle manager."""

    def test_is_installed_true(self):
        from phone_cli.adb.companion_manager import CompanionManager

        mgr = CompanionManager(device_id="test123")
        with patch.object(
            mgr,
            "_run_adb",
            return_value=MagicMock(
                stdout="package:com.gamehelper.androidcontrol\npackage:com.other"
            ),
        ):
            assert mgr.is_installed() is True

    def test_is_installed_false(self):
        from phone_cli.adb.companion_manager import CompanionManager

        mgr = CompanionManager(device_id="test123")
        with patch.object(
            mgr,
            "_run_adb",
            return_value=MagicMock(stdout="package:com.other.app"),
        ):
            assert mgr.is_installed() is False

    def test_is_accessibility_enabled_true(self):
        from phone_cli.adb.companion_manager import CompanionManager, COMPANION_SERVICE

        mgr = CompanionManager()
        with patch.object(mgr, "is_accessibility_globally_enabled", return_value=True), \
             patch.object(mgr, "is_accessibility_service_enabled", return_value=True):
            assert mgr.is_accessibility_enabled() is True

    def test_is_accessibility_enabled_false(self):
        from phone_cli.adb.companion_manager import CompanionManager

        mgr = CompanionManager()
        with patch.object(mgr, "is_accessibility_globally_enabled", return_value=False), \
             patch.object(mgr, "is_accessibility_service_enabled", return_value=True):
            assert mgr.is_accessibility_enabled() is False

    def test_is_port_forwarded_true(self):
        from phone_cli.adb.companion_manager import CompanionManager

        mgr = CompanionManager()
        with patch.object(
            mgr,
            "_run_adb",
            return_value=MagicMock(
                stdout="abc123 tcp:17342 tcp:17342\nabc123 tcp:17343 tcp:17343"
            ),
        ):
            assert mgr.is_port_forwarded() is True

    def test_is_port_forwarded_false(self):
        from phone_cli.adb.companion_manager import CompanionManager

        mgr = CompanionManager()
        with patch.object(
            mgr, "_run_adb", return_value=MagicMock(stdout="")
        ):
            assert mgr.is_port_forwarded() is False

    def test_get_installed_version(self):
        from phone_cli.adb.companion_manager import CompanionManager

        mgr = CompanionManager()
        with patch.object(
            mgr,
            "_run_adb",
            return_value=MagicMock(stdout="    versionName=1.2.3\n    versionCode=10"),
        ):
            assert mgr.get_installed_version() == "1.2.3"

    def test_get_status_full(self):
        from phone_cli.adb.companion_manager import CompanionManager

        mgr = CompanionManager()
        with patch.object(mgr, "get_device_state", return_value="device"), \
             patch.object(mgr, "is_installed", return_value=True), \
             patch.object(mgr, "get_installed_version", return_value="1.0.0"), \
             patch.object(mgr, "is_accessibility_globally_enabled", return_value=True), \
             patch.object(mgr, "is_accessibility_service_enabled", return_value=True), \
             patch.object(
                 mgr,
                 "get_accessibility_runtime_state",
                 return_value={
                     "service_enabled_in_manager": True,
                     "service_bound": True,
                     "service_crashed": False,
                 },
             ), \
             patch.object(mgr, "is_companion_process_running", return_value=True), \
             patch.object(mgr, "is_port_forwarded", return_value=True), \
             patch.object(
                 mgr._client,
                 "get_status",
                 return_value={
                     "ready": True,
                     "serviceConnected": True,
                     "snapshotAvailable": True,
                     "httpServerRunning": True,
                     "webSocketServerRunning": True,
                 },
             ):
            status = mgr.get_status()
            assert status["installed"] is True
            assert status["version"] == "1.0.0"
            assert status["accessibility_enabled"] is True
            assert status["accessibility_service_bound"] is True
            assert status["accessibility_service_bound_raw"] is True
            assert status["port_forwarded"] is True
            assert status["service_ready"] is True
            assert status["runtime_service_connected"] is True
            assert status["snapshot_available"] is True
            assert status["http_server_running"] is True
            assert status["web_socket_server_running"] is True
            assert status["ready"] is True
            assert status["issue_codes"] == []
            assert status["issues"] == []

    def test_get_status_uses_runtime_health_when_dumpsys_bound_is_false(self):
        from phone_cli.adb.companion_manager import CompanionManager

        mgr = CompanionManager(device_id="test123")
        with patch.object(mgr, "get_device_state", return_value="device"), \
             patch.object(mgr, "is_installed", return_value=True), \
             patch.object(mgr, "get_installed_version", return_value="1.0.0"), \
             patch.object(mgr, "is_accessibility_globally_enabled", return_value=True), \
             patch.object(mgr, "is_accessibility_service_enabled", return_value=True), \
             patch.object(
                 mgr,
                 "get_accessibility_runtime_state",
                 return_value={
                     "service_enabled_in_manager": True,
                     "service_bound": False,
                     "service_crashed": False,
                     "enabled_services_raw": "{service}",
                     "bound_services_raw": "{}",
                     "crashed_services_raw": "{}",
                 },
             ), \
             patch.object(mgr, "is_companion_process_running", return_value=True), \
             patch.object(mgr, "is_port_forwarded", return_value=True), \
             patch.object(
                 mgr._client,
                 "get_status",
                 return_value={
                     "ready": True,
                     "serviceConnected": True,
                     "snapshotAvailable": True,
                     "httpServerRunning": True,
                     "webSocketServerRunning": True,
                 },
             ):
            status = mgr.get_status()

        assert status["accessibility_service_bound"] is True
        assert status["accessibility_service_bound_raw"] is False
        assert status["ready"] is True
        assert status["issues"] == []
        assert status["diagnostic_notes"]

    def test_get_status_reports_crashed_service(self):
        from phone_cli.adb.companion_manager import CompanionManager

        mgr = CompanionManager(device_id="test123")
        with patch.object(mgr, "get_device_state", return_value="device"), \
             patch.object(mgr, "is_installed", return_value=True), \
             patch.object(mgr, "get_installed_version", return_value="1.0.0"), \
             patch.object(mgr, "is_accessibility_globally_enabled", return_value=True), \
             patch.object(mgr, "is_accessibility_service_enabled", return_value=True), \
             patch.object(
                 mgr,
                 "get_accessibility_runtime_state",
                 return_value={
                     "service_enabled_in_manager": True,
                     "service_bound": False,
                     "service_crashed": True,
                 },
             ), \
             patch.object(mgr, "is_companion_process_running", return_value=False), \
             patch.object(mgr, "is_port_forwarded", return_value=False):
            status = mgr.get_status()

        assert status["ready"] is False
        assert "辅助服务已被系统标记为 crashed" in status["issues"]
        assert "SERVICE_CRASHED" in status["issue_codes"]
        assert status["recommended_action"] is not None

    def test_get_status_reports_startup_error(self):
        from phone_cli.adb.companion_manager import CompanionManager

        mgr = CompanionManager(device_id="test123")
        with patch.object(mgr, "get_device_state", return_value="device"), \
             patch.object(mgr, "is_installed", return_value=True), \
             patch.object(mgr, "get_installed_version", return_value="1.0.0"), \
             patch.object(mgr, "is_accessibility_globally_enabled", return_value=True), \
             patch.object(mgr, "is_accessibility_service_enabled", return_value=True), \
             patch.object(
                 mgr,
                 "get_accessibility_runtime_state",
                 return_value={
                     "service_enabled_in_manager": True,
                     "service_bound": True,
                     "service_crashed": False,
                     "enabled_services_raw": "{service}",
                     "bound_services_raw": "{service}",
                     "crashed_services_raw": "{}",
                 },
             ), \
             patch.object(mgr, "is_companion_process_running", return_value=True), \
             patch.object(mgr, "is_port_forwarded", return_value=True), \
             patch.object(
                 mgr._client,
                 "get_status",
                 return_value={
                     "ready": False,
                     "serviceConnected": True,
                     "snapshotAvailable": False,
                     "httpServerRunning": False,
                     "webSocketServerRunning": False,
                     "startupError": "BindException: Address already in use",
                 },
             ):
            status = mgr.get_status()

        assert status["ready"] is False
        assert status["startup_error"] == "BindException: Address already in use"
        assert "SERVICE_STARTUP_ERROR" in status["issue_codes"]

    def test_adb_prefix_with_device_id(self):
        from phone_cli.adb.companion_manager import CompanionManager

        mgr = CompanionManager(device_id="abc123")
        assert mgr._adb() == ["adb", "-s", "abc123"]

    def test_adb_prefix_without_device_id(self):
        from phone_cli.adb.companion_manager import CompanionManager

        mgr = CompanionManager()
        assert mgr._adb() == ["adb"]


# ── Command dispatch tests for companion commands ────────────────────

class TestCompanionCommands:
    """Tests for the companion command handlers via dispatch_command."""

    def _make_adb_daemon(self):
        daemon = MagicMock()
        daemon._read_state.return_value = {"device_type": "adb"}
        return daemon

    def _make_ios_daemon(self):
        daemon = MagicMock()
        daemon._read_state.return_value = {"device_type": "ios"}
        return daemon

    def test_companion_status_adb(self):
        daemon = self._make_adb_daemon()
        with patch(
            "phone_cli.adb.companion_manager.CompanionManager"
        ) as MockMgr:
            MockMgr.return_value.get_status.return_value = {
                "installed": True,
                "service_ready": True,
            }
            result = dispatch_command("companion_status", {}, daemon)
        parsed = json.loads(result)
        assert parsed["status"] == "ok"
        assert parsed["data"]["installed"] is True

    def test_companion_preflight_adb(self):
        daemon = self._make_adb_daemon()
        with patch(
            "phone_cli.adb.companion_manager.CompanionManager"
        ) as MockMgr:
            MockMgr.return_value.get_status.return_value = {
                "ready": False,
                "issues": ["辅助服务已被系统标记为 crashed"],
                "recommended_action": "辅助服务已崩溃，请在手机上关闭后重新启用该无障碍服务，再重新执行 preflight。",
            }
            result = dispatch_command("companion_preflight", {}, daemon)
        parsed = json.loads(result)
        assert parsed["status"] == "ok"
        assert parsed["data"]["ready"] is False
        assert parsed["data"]["issues"]

    def test_companion_status_ios_rejected(self):
        daemon = self._make_ios_daemon()
        result = dispatch_command("companion_status", {}, daemon)
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["error_code"] == ErrorCode.UNSUPPORTED_OPERATION

    def test_companion_setup_adb(self):
        daemon = self._make_adb_daemon()
        with patch(
            "phone_cli.adb.companion_manager.CompanionManager"
        ) as MockMgr:
            MockMgr.return_value.ensure_ready.return_value = {
                "available": True,
                "steps": [],
            }
            result = dispatch_command("companion_setup", {}, daemon)
        parsed = json.loads(result)
        assert parsed["status"] == "ok"
        assert parsed["data"]["available"] is True
        # Should have written companion_status to state
        daemon._write_state.assert_called()

    def test_companion_setup_ios_rejected(self):
        daemon = self._make_ios_daemon()
        result = dispatch_command("companion_setup", {}, daemon)
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["error_code"] == ErrorCode.UNSUPPORTED_OPERATION

    def test_find_nodes_success(self):
        daemon = self._make_adb_daemon()
        with patch("phone_cli.adb.companion.CompanionClient") as MockClient:
            MockClient.return_value.find_nodes.return_value = {
                "totalMatches": 2,
                "nodes": [{"nodeId": "0.1"}, {"nodeId": "0.2"}],
            }
            result = dispatch_command(
                "find_nodes", {"text": "登录", "clickable": True}, daemon
            )
        parsed = json.loads(result)
        assert parsed["status"] == "ok"
        assert parsed["data"]["totalMatches"] == 2

    def test_search_click_success(self):
        daemon = self._make_adb_daemon()
        with patch("phone_cli.adb.companion.CompanionClient") as MockClient:
            mock_client = MockClient.return_value
            mock_client.is_ready.return_value = True
            mock_client.search_and_click.return_value = {
                "success": True,
                "action": "search_click",
                "totalMatches": 1,
            }
            result = dispatch_command(
                "search_click", {"text_contains": "动态", "clickable": True}, daemon
            )
        parsed = json.loads(result)
        assert parsed["status"] == "ok"
        assert parsed["data"]["success"] is True

    def test_search_set_text_requires_text(self):
        daemon = self._make_adb_daemon()
        result = dispatch_command("search_set_text", {}, daemon)
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["error_code"] == ErrorCode.COMMAND_FAILED

    def test_search_set_text_success(self):
        daemon = self._make_adb_daemon()
        with patch("phone_cli.adb.companion.CompanionClient") as MockClient:
            mock_client = MockClient.return_value
            mock_client.is_ready.return_value = True
            mock_client.search_and_set_text.return_value = {
                "success": True,
                "action": "search_set_text",
                "typedText": "hello",
            }
            result = dispatch_command(
                "search_set_text", {"text": "hello", "class_name": "android.widget.EditText"}, daemon
            )
        parsed = json.loads(result)
        assert parsed["status"] == "ok"
        assert parsed["data"]["success"] is True

    def test_find_nodes_companion_unavailable(self):
        daemon = self._make_adb_daemon()
        from phone_cli.adb.companion import CompanionUnavailableError

        with patch("phone_cli.adb.companion.CompanionClient") as MockClient:
            MockClient.return_value.find_nodes.side_effect = (
                CompanionUnavailableError("not reachable")
            )
            result = dispatch_command("find_nodes", {"text": "test"}, daemon)
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["error_code"] == ErrorCode.COMPANION_UNAVAILABLE

    def test_click_node_success(self):
        daemon = self._make_adb_daemon()
        with patch("phone_cli.adb.companion.CompanionClient") as MockClient:
            MockClient.return_value.click_node.return_value = {
                "success": True,
                "source": "companion",
            }
            result = dispatch_command(
                "click_node",
                {"node_id": "0.3.1", "fallback_x": 200, "fallback_y": 300},
                daemon,
            )
        parsed = json.loads(result)
        assert parsed["status"] == "ok"
        assert parsed["data"]["success"] is True

    def test_click_node_missing_id(self):
        daemon = self._make_adb_daemon()
        result = dispatch_command("click_node", {}, daemon)
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["error_code"] == ErrorCode.COMMAND_FAILED

    def test_screen_context_success(self):
        daemon = self._make_adb_daemon()
        with patch("phone_cli.adb.companion.CompanionClient") as MockClient:
            MockClient.return_value.get_screen_context.return_value = {
                "packageName": "com.example",
                "clickableNodes": [{"text": "OK"}],
                "editableNodes": [],
            }
            result = dispatch_command("screen_context", {}, daemon)
        parsed = json.loads(result)
        assert parsed["status"] == "ok"
        assert parsed["data"]["packageName"] == "com.example"

    def test_screen_context_ios_rejected(self):
        daemon = self._make_ios_daemon()
        result = dispatch_command("screen_context", {}, daemon)
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["error_code"] == ErrorCode.UNSUPPORTED_OPERATION


# ── UI tree routing tests ────────────────────────────────────────────

class TestUiTreeRouting:
    """Tests for the companion-first UI tree routing."""

    def test_ui_tree_adb_uses_companion_when_ready(self):
        daemon = MagicMock()
        daemon._read_state.return_value = {"device_type": "adb"}

        with patch("phone_cli.adb.companion.CompanionClient") as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.is_ready.return_value = True
            mock_instance.get_ui_tree.return_value = {
                "capturedAt": "2024-01-01T00:00:00",
                "root": {
                    "nodeId": "0",
                    "className": "android.widget.FrameLayout",
                    "text": "",
                    "clickable": False,
                    "scrollable": False,
                    "editable": False,
                    "children": [
                        {
                            "nodeId": "0.1",
                            "className": "android.widget.Button",
                            "text": "OK",
                            "resourceId": "com.example:id/btn_ok",
                            "clickable": True,
                            "scrollable": False,
                            "editable": False,
                            "bounds": {"left": 100, "top": 200, "right": 300, "bottom": 260},
                            "center": {"x": 200, "y": 230},
                            "children": [],
                        }
                    ],
                },
            }
            result = dispatch_command("ui_tree", {}, daemon)

        parsed = json.loads(result)
        assert parsed["status"] == "ok"
        assert parsed["data"]["source"] == "companion"
        elements = parsed["data"]["elements"]
        assert len(elements) == 1
        assert elements[0]["text"] == "OK"
        assert elements[0]["node_id"] == "0.1"
        assert elements[0]["clickable"] is True
        assert elements[0]["center_x"] == 200
        assert elements[0]["center_y"] == 230

    def test_ui_tree_adb_falls_back_to_uiautomator(self):
        daemon = MagicMock()
        daemon._read_state.return_value = {"device_type": "adb"}

        with patch("phone_cli.adb.companion.CompanionClient") as MockClient, \
             patch("phone_cli.cli.commands.subprocess") as mock_subproc:
            mock_instance = MockClient.return_value
            mock_instance.is_ready.return_value = False

            # Mock uiautomator dump and cat
            dump_result = MagicMock(returncode=0)
            cat_result = MagicMock(
                returncode=0,
                stdout='<?xml version="1.0" ?><hierarchy><node text="Hello" resource-id="id/txt" class="TextView" bounds="[0,0][100,100]" /></hierarchy>',
            )
            mock_subproc.run.side_effect = [dump_result, cat_result]

            result = dispatch_command("ui_tree", {}, daemon)

        parsed = json.loads(result)
        assert parsed["status"] == "ok"
        assert parsed["data"]["source"] == "uiautomator"
        assert len(parsed["data"]["elements"]) == 1
        assert parsed["data"]["elements"][0]["text"] == "Hello"

    def test_ui_tree_adb_returns_error_when_dump_fails(self):
        daemon = MagicMock()
        daemon._read_state.return_value = {"device_type": "adb"}

        with patch("phone_cli.adb.companion.CompanionClient") as MockClient, \
             patch("phone_cli.cli.commands.subprocess") as mock_subproc:
            mock_instance = MockClient.return_value
            mock_instance.is_ready.return_value = False
            mock_subproc.run.return_value = MagicMock(returncode=1, stdout="", stderr="dump failed")

            result = dispatch_command("ui_tree", {}, daemon)

        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["error_code"] == "UI_TREE_UNAVAILABLE"
        assert mock_subproc.run.call_count == 1


# ── Type command companion integration test ──────────────────────────

class TestTypeCommandCompanion:
    """Tests for the enhanced type command with companion integration."""

    def test_type_uses_companion_when_available(self):
        daemon = MagicMock()
        daemon._read_state.return_value = {"device_type": "adb"}

        with patch("phone_cli.adb.companion.CompanionClient") as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.is_ready.return_value = True
            mock_instance.set_text.return_value = {"success": True}

            result = dispatch_command("type", {"text": "hello"}, daemon)

        parsed = json.loads(result)
        assert parsed["status"] == "ok"
        assert parsed["data"]["typed"] == "hello"
        assert parsed["data"]["source"] == "companion"

    def test_type_falls_back_to_adb_keyboard(self):
        daemon = MagicMock()
        daemon._read_state.return_value = {"device_type": "adb"}

        with patch("phone_cli.adb.companion.CompanionClient") as MockClient, \
             patch("phone_cli.adb.detect_and_set_adb_keyboard", return_value="orig_ime"), \
             patch("phone_cli.adb.clear_text"), \
             patch("phone_cli.adb.type_text"), \
             patch("phone_cli.adb.restore_keyboard"):
            mock_instance = MockClient.return_value
            mock_instance.is_ready.return_value = False

            result = dispatch_command("type", {"text": "hello"}, daemon)

        parsed = json.loads(result)
        assert parsed["status"] == "ok"
        assert parsed["data"]["typed"] == "hello"


# ── Normalize companion tree tests ───────────────────────────────────

class TestNormalizeCompanionTree:
    """Tests for _normalize_companion_tree."""

    def test_flattens_nested_tree(self):
        from phone_cli.cli.commands import _normalize_companion_tree

        tree = {
            "root": {
                "nodeId": "0",
                "className": "FrameLayout",
                "text": "",
                "clickable": False,
                "scrollable": False,
                "editable": False,
                "children": [
                    {
                        "nodeId": "0.0",
                        "className": "Button",
                        "text": "Submit",
                        "clickable": True,
                        "scrollable": False,
                        "editable": False,
                        "bounds": {"left": 10, "top": 20, "right": 110, "bottom": 70},
                        "children": [],
                    },
                    {
                        "nodeId": "0.1",
                        "className": "EditText",
                        "text": "",
                        "contentDescription": "Search",
                        "editable": True,
                        "clickable": False,
                        "scrollable": False,
                        "center": {"x": 540, "y": 100},
                        "children": [],
                    },
                ],
            }
        }
        elements = _normalize_companion_tree(tree)
        assert len(elements) == 2

        btn = elements[0]
        assert btn["text"] == "Submit"
        assert btn["node_id"] == "0.0"
        assert btn["clickable"] is True
        assert btn["bounds"] == "[10,20][110,70]"
        assert btn["center_x"] == 60
        assert btn["center_y"] == 45

        edit = elements[1]
        assert edit["content_description"] == "Search"
        assert edit["editable"] is True
        assert edit["center_x"] == 540

    def test_empty_tree(self):
        from phone_cli.cli.commands import _normalize_companion_tree

        assert _normalize_companion_tree({}) == []
        assert _normalize_companion_tree({"root": None}) == []

    def test_skips_nodes_without_info(self):
        from phone_cli.cli.commands import _normalize_companion_tree

        tree = {
            "root": {
                "nodeId": "0",
                "className": "FrameLayout",
                "text": "",
                "clickable": False,
                "scrollable": False,
                "editable": False,
                "children": [],
            }
        }
        elements = _normalize_companion_tree(tree)
        assert len(elements) == 0


# ── Error code tests ─────────────────────────────────────────────────

class TestCompanionErrorCodes:
    """Tests for companion error codes in output.py."""

    def test_companion_unavailable_code_exists(self):
        assert ErrorCode.COMPANION_UNAVAILABLE == "COMPANION_UNAVAILABLE"

    def test_companion_build_failed_code_exists(self):
        assert ErrorCode.COMPANION_BUILD_FAILED == "COMPANION_BUILD_FAILED"


# ── ensure_ready() flow tests ────────────────────────────────────────

class TestCompanionManagerEnsureReady:
    """Tests for the ensure_ready() decision chain."""

    def _make_manager(self):
        from phone_cli.adb.companion_manager import CompanionManager
        mgr = CompanionManager(device_id="test123")
        return mgr

    def _healthy_status(self):
        return {
            "issues": [],
            "issue_codes": [],
            "accessibility_enabled": True,
            "accessibility_service_bound": True,
            "accessibility_service_crashed": False,
            "service_ready": True,
        }

    def _unbound_status(self):
        return {
            "issues": ["辅助服务未绑定到 AccessibilityManager"],
            "issue_codes": ["SERVICE_NOT_BOUND"],
            "accessibility_enabled": True,
            "accessibility_service_bound": False,
            "accessibility_service_crashed": False,
            "service_ready": False,
        }

    def test_ensure_ready_full_happy_path(self):
        mgr = self._make_manager()
        with patch.object(mgr, "get_device_state", return_value="device"), \
             patch.object(mgr, "is_installed", return_value=True), \
             patch.object(mgr, "is_accessibility_enabled", return_value=True), \
             patch.object(mgr, "get_status", return_value=self._healthy_status()), \
             patch.object(mgr, "is_port_forwarded", return_value=True), \
             patch.object(mgr._client, "is_ready", return_value=True):
            result = mgr.ensure_ready()
        assert result["available"] is True
        assert len(result["steps"]) == 5

    def test_ensure_ready_installs_when_not_installed(self):
        mgr = self._make_manager()
        with patch.object(mgr, "get_device_state", return_value="device"), \
             patch.object(mgr, "is_installed", return_value=False), \
             patch.object(mgr, "install", return_value={"installed": True}) as mock_install, \
             patch.object(mgr, "is_accessibility_enabled", return_value=True), \
             patch.object(mgr, "get_status", return_value=self._healthy_status()), \
             patch.object(mgr, "is_port_forwarded", return_value=True), \
             patch.object(mgr._client, "is_ready", return_value=True):
            result = mgr.ensure_ready()
        mock_install.assert_called_once()
        assert result["available"] is True

    def test_ensure_ready_install_failure_returns_error(self):
        mgr = self._make_manager()
        with patch.object(mgr, "get_device_state", return_value="device"), \
             patch.object(mgr, "is_installed", return_value=False), \
             patch.object(mgr, "install", side_effect=RuntimeError("disk full")):
            result = mgr.ensure_ready()
        assert result["available"] is False
        assert "disk full" in result["error"]

    def test_ensure_ready_enables_accessibility_when_disabled(self):
        mgr = self._make_manager()
        with patch.object(mgr, "get_device_state", return_value="device"), \
             patch.object(mgr, "is_installed", return_value=True), \
             patch.object(mgr, "is_accessibility_enabled", return_value=False), \
             patch.object(mgr, "enable_accessibility", return_value={"enabled": True}) as mock_enable, \
             patch.object(mgr, "get_status", return_value=self._healthy_status()), \
             patch.object(mgr, "is_port_forwarded", return_value=True), \
             patch.object(mgr._client, "is_ready", return_value=True):
            result = mgr.ensure_ready()
        mock_enable.assert_called_once()
        assert result["available"] is True

    def test_ensure_ready_recovers_enabled_but_unbound_service(self):
        mgr = self._make_manager()
        with patch.object(mgr, "get_device_state", return_value="device"), \
             patch.object(mgr, "is_installed", return_value=True), \
             patch.object(mgr, "is_accessibility_enabled", return_value=True), \
             patch.object(mgr, "get_status", side_effect=[
                 self._unbound_status(),
                 self._healthy_status(),
             ]), \
             patch.object(mgr, "is_port_forwarded", return_value=True), \
             patch.object(mgr._client, "is_ready", side_effect=[False, True]), \
             patch.object(mgr, "_run_adb") as mock_adb, \
             patch("phone_cli.adb.companion_manager.time.sleep"):
            result = mgr.ensure_ready()

        assert result["available"] is True
        assert any("binding_recovery" in step for step in result["steps"])
        assert mock_adb.called

    def test_ensure_ready_accessibility_enable_failure_returns_error(self):
        mgr = self._make_manager()
        with patch.object(mgr, "get_device_state", return_value="device"), \
             patch.object(mgr, "is_installed", return_value=True), \
             patch.object(mgr, "is_accessibility_enabled", return_value=False), \
             patch.object(mgr, "enable_accessibility", return_value={
                 "enabled": False, "message": "OEM blocked"
             }):
            result = mgr.ensure_ready()
        assert result["available"] is False
        assert "OEM blocked" in result["error"]

    def test_ensure_ready_sets_up_port_forward_before_readiness_check(self):
        """Port forwarding must happen BEFORE the readiness poll."""
        mgr = self._make_manager()
        call_order = []

        def mock_setup():
            call_order.append("port_forward")
            return {"forwarded": True, "http_port": 17342, "ws_port": 17343}

        def mock_is_ready():
            call_order.append("is_ready")
            return True

        with patch.object(mgr, "get_device_state", return_value="device"), \
             patch.object(mgr, "is_installed", return_value=True), \
             patch.object(mgr, "is_accessibility_enabled", return_value=True), \
             patch.object(mgr, "get_status", return_value=self._healthy_status()), \
             patch.object(mgr, "is_port_forwarded", return_value=False), \
             patch.object(mgr, "setup_port_forward", side_effect=mock_setup), \
             patch.object(mgr._client, "is_ready", side_effect=mock_is_ready):
            result = mgr.ensure_ready()

        assert result["available"] is True
        # port_forward must come before is_ready
        assert call_order.index("port_forward") < call_order.index("is_ready")

    def test_ensure_ready_port_forward_failure_returns_error(self):
        mgr = self._make_manager()
        with patch.object(mgr, "get_device_state", return_value="device"), \
             patch.object(mgr, "is_installed", return_value=True), \
             patch.object(mgr, "is_accessibility_enabled", return_value=True), \
             patch.object(mgr, "get_status", return_value=self._healthy_status()), \
             patch.object(mgr, "is_port_forwarded", return_value=False), \
             patch.object(mgr, "setup_port_forward", side_effect=RuntimeError("port busy")):
            result = mgr.ensure_ready()
        assert result["available"] is False
        assert "port busy" in result["error"]

    def test_ensure_ready_retries_launch_when_not_ready(self):
        mgr = self._make_manager()
        ready_calls = [False, False, True]  # Becomes ready on 3rd check

        with patch.object(mgr, "get_device_state", return_value="device"), \
             patch.object(mgr, "is_installed", return_value=True), \
             patch.object(mgr, "is_accessibility_enabled", return_value=True), \
             patch.object(mgr, "get_status", return_value=self._healthy_status()), \
             patch.object(mgr, "is_port_forwarded", return_value=True), \
             patch.object(mgr._client, "is_ready", side_effect=ready_calls), \
             patch.object(mgr, "_run_adb") as mock_adb, \
             patch("phone_cli.adb.companion_manager.time.sleep"):
            result = mgr.ensure_ready()

        assert result["available"] is True
        # Should have launched MainActivity to wake up the service
        mock_adb.assert_called()


class TestCompanionManagerStrictOem:
    """OEM-aware binding recovery (Huawei/MIUI/ColorOS/Funtouch …)."""

    def _make_manager(self, brand: str = ""):
        from phone_cli.adb.companion_manager import CompanionManager
        mgr = CompanionManager(device_id="test-strict")
        mgr._cached_brand = brand.lower()
        return mgr

    def test_is_strict_oem_recognises_known_brands(self):
        for brand in ("HUAWEI", "Honor", "Xiaomi", "REDMI", "OPPO", "OnePlus",
                      "realme", "vivo", "iQOO", "MEIZU"):
            mgr = self._make_manager(brand=brand)
            assert mgr.is_strict_oem(), f"{brand} should be strict-OEM"

    def test_is_strict_oem_returns_false_for_aosp_and_samsung(self):
        for brand in ("samsung", "google", "asus", ""):
            mgr = self._make_manager(brand=brand)
            assert not mgr.is_strict_oem(), f"{brand} should not be strict"

    def test_force_rebind_clears_then_restores_settings(self):
        mgr = self._make_manager(brand="huawei")
        with patch.object(mgr, "_run_adb") as mock_adb, \
             patch("phone_cli.adb.companion_manager.time.sleep"):
            result = mgr.force_rebind_accessibility()

        assert "force_stop_companion" in result["actions"]
        assert "clear_accessibility_settings" in result["actions"]
        assert "restore_accessibility_settings" in result["actions"]

        # Verify ordering: force-stop -> clear -> restore
        run_calls = [call.args for call in mock_adb.call_args_list]
        joined = ["|".join(str(arg) for arg in args) for args in run_calls]
        assert any("force-stop" in s for s in joined)

        empty_clear_idx = next(
            i for i, s in enumerate(joined)
            if "enabled_accessibility_services" in s and ('""' in s or "''" in s)
        )
        restore_idx = next(
            i for i, s in enumerate(joined)
            if "enabled_accessibility_services" in s
            and "com.gamehelper.androidcontrol" in s
        )
        assert empty_clear_idx < restore_idx

    def test_attempt_binding_recovery_strict_oem_skips_light_path(self):
        """Strict OEMs should jump straight to force_rebind without trying am-start.

        am-start is wasted work on these ROMs because AMS won't re-evaluate.
        """
        mgr = self._make_manager(brand="huawei")

        with patch.object(mgr, "force_rebind_accessibility", return_value={"actions": ["x"]}) as mock_rebind, \
             patch.object(mgr, "add_to_battery_whitelist", return_value=True) as mock_whitelist, \
             patch.object(mgr, "_poll_ready", return_value=True), \
             patch.object(mgr, "get_status", return_value={"accessibility_service_bound": True}), \
             patch.object(mgr, "_run_adb") as mock_adb:
            recovery = mgr._attempt_binding_recovery()

        assert recovery["recovered"] is True
        assert recovery["strict_oem"] is True
        mock_rebind.assert_called_once()
        mock_whitelist.assert_called_once()
        # No am start launched on the light path for strict OEMs
        assert all(
            "am" not in call.args or "start" not in call.args
            for call in mock_adb.call_args_list
        )

    def test_attempt_binding_recovery_non_strict_uses_light_path_first(self):
        mgr = self._make_manager(brand="google")

        with patch.object(mgr, "force_rebind_accessibility") as mock_rebind, \
             patch.object(mgr, "_poll_ready", side_effect=[True]), \
             patch.object(mgr, "_run_adb"):
            recovery = mgr._attempt_binding_recovery()

        assert recovery["recovered"] is True
        mock_rebind.assert_not_called()  # light path succeeded

    def test_attempt_binding_recovery_non_strict_falls_through_to_force_rebind(self):
        mgr = self._make_manager(brand="google")

        with patch.object(mgr, "force_rebind_accessibility", return_value={"actions": ["x"]}) as mock_rebind, \
             patch.object(mgr, "_poll_ready", side_effect=[False, False, True]), \
             patch.object(mgr, "get_status", return_value={"accessibility_service_bound": True}), \
             patch.object(mgr, "_run_adb"):
            recovery = mgr._attempt_binding_recovery()

        assert recovery["recovered"] is True
        mock_rebind.assert_called_once()  # light path failed, force_rebind was needed

    def test_enable_accessibility_adds_battery_whitelist_on_strict_oem(self):
        mgr = self._make_manager(brand="xiaomi")

        with patch.object(mgr, "_run_adb", return_value=MagicMock(stdout="")) as _mock_adb, \
             patch.object(mgr, "add_to_battery_whitelist", return_value=True) as mock_whitelist, \
             patch.object(mgr, "get_status", return_value={
                 "accessibility_enabled": True,
                 "accessibility_service_bound": True,
                 "issues": [],
                 "issue_codes": [],
             }), \
             patch("phone_cli.adb.companion_manager.time.sleep"):
            result = mgr.enable_accessibility()

        assert result["enabled"] is True
        mock_whitelist.assert_called_once()

    def test_enable_accessibility_skips_battery_whitelist_on_aosp(self):
        mgr = self._make_manager(brand="google")

        with patch.object(mgr, "_run_adb", return_value=MagicMock(stdout="")), \
             patch.object(mgr, "add_to_battery_whitelist", return_value=True) as mock_whitelist, \
             patch.object(mgr, "get_status", return_value={
                 "accessibility_enabled": True,
                 "accessibility_service_bound": True,
                 "issues": [],
                 "issue_codes": [],
             }), \
             patch("phone_cli.adb.companion_manager.time.sleep"):
            mgr.enable_accessibility()

        mock_whitelist.assert_not_called()

    def test_add_to_battery_whitelist_is_idempotent(self):
        mgr = self._make_manager(brand="huawei")

        with patch.object(mgr, "_run_adb") as mock_adb:
            assert mgr.add_to_battery_whitelist() is True
            assert mgr.add_to_battery_whitelist() is True  # second call no-op
        assert mock_adb.call_count == 1


# ── Normalize companion tree malformed input tests ───────────────────

class TestNormalizeCompanionTreeMalformed:
    """Tests for _normalize_companion_tree with unexpected input."""

    def test_node_without_bounds(self):
        from phone_cli.cli.commands import _normalize_companion_tree

        tree = {
            "root": {
                "nodeId": "0",
                "text": "Hello",
                "clickable": True,
                "scrollable": False,
                "editable": False,
                "children": [],
            }
        }
        elements = _normalize_companion_tree(tree)
        assert len(elements) == 1
        assert elements[0]["bounds"] == ""
        assert "center_x" not in elements[0]

    def test_node_without_children_key(self):
        from phone_cli.cli.commands import _normalize_companion_tree

        tree = {
            "root": {
                "nodeId": "0",
                "text": "No children key",
                "clickable": False,
                "scrollable": False,
                "editable": False,
                # No "children" key at all
            }
        }
        elements = _normalize_companion_tree(tree)
        assert len(elements) == 1
        assert elements[0]["text"] == "No children key"

    def test_node_with_partial_bounds(self):
        from phone_cli.cli.commands import _normalize_companion_tree

        tree = {
            "root": {
                "nodeId": "0",
                "text": "Partial",
                "clickable": True,
                "scrollable": False,
                "editable": False,
                "bounds": {"left": 10},  # Missing top, right, bottom
                "children": [],
            }
        }
        elements = _normalize_companion_tree(tree)
        assert len(elements) == 1
        assert elements[0]["bounds"] == "[10,0][0,0]"

    def test_deeply_nested_tree(self):
        from phone_cli.cli.commands import _normalize_companion_tree

        tree = {
            "root": {
                "nodeId": "0",
                "text": "",
                "clickable": False,
                "scrollable": False,
                "editable": False,
                "children": [{
                    "nodeId": "0.0",
                    "text": "",
                    "clickable": False,
                    "scrollable": False,
                    "editable": False,
                    "children": [{
                        "nodeId": "0.0.0",
                        "text": "Deep",
                        "clickable": True,
                        "scrollable": False,
                        "editable": False,
                        "children": [],
                    }],
                }],
            }
        }
        elements = _normalize_companion_tree(tree)
        assert len(elements) == 1
        assert elements[0]["node_id"] == "0.0.0"
        assert elements[0]["text"] == "Deep"


# ── IPC timeout tests ────────────────────────────────────────────────

class TestIPCTimeout:
    """Tests for command timeout configuration."""

    def test_companion_setup_timeout_is_300(self):
        from phone_cli.cli.daemon import PhoneCLIDaemon
        import tempfile

        daemon = PhoneCLIDaemon(home_dir=tempfile.mkdtemp())
        assert daemon._get_command_timeout("companion_setup", {}) == 300.0

    def test_default_timeout_is_15(self):
        from phone_cli.cli.daemon import PhoneCLIDaemon
        import tempfile

        daemon = PhoneCLIDaemon(home_dir=tempfile.mkdtemp())
        assert daemon._get_command_timeout("companion_status", {}) == 15.0


# ── setup_port_forward error handling tests ──────────────────────────

class TestSetupPortForward:
    """Tests for setup_port_forward return code checking."""

    def test_port_forward_success(self):
        from phone_cli.adb.companion_manager import CompanionManager

        mgr = CompanionManager()
        with patch.object(
            mgr,
            "_run_adb",
            return_value=MagicMock(returncode=0, stdout="", stderr=""),
        ):
            result = mgr.setup_port_forward()
        assert result["forwarded"] is True

    def test_port_forward_failure_raises(self):
        from phone_cli.adb.companion_manager import CompanionManager
        import pytest

        mgr = CompanionManager()
        with patch.object(
            mgr,
            "_run_adb",
            return_value=MagicMock(returncode=1, stdout="", stderr="error: device not found"),
        ):
            with pytest.raises(RuntimeError, match="port forward failed"):
                mgr.setup_port_forward()
