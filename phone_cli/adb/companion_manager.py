"""Build, install, enable, and manage the Android Companion accessibility service."""

import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from phone_cli.adb.companion import CompanionClient, CompanionUnavailableError

# ── Constants ────────────────────────────────────────────────────────

COMPANION_PACKAGE = "com.gamehelper.androidcontrol"
COMPANION_SERVICE = (
    "com.gamehelper.androidcontrol/"
    "com.google.android.accessibility.selecttospeak.SelectToSpeakService"
)
COMPANION_MAIN_ACTIVITY = "com.gamehelper.androidcontrol/.MainActivity"
COMPANION_HTTP_PORT = 17342
COMPANION_WS_PORT = 17343

COMPANION_PROJECT_DIR = Path(__file__).resolve().parents[2] / "android-companion"
APK_PATH = COMPANION_PROJECT_DIR / "app" / "build" / "outputs" / "apk" / "debug" / "app-debug.apk"


class CompanionManager:
    """Full lifecycle manager for the Android Companion app.

    Handles: build from source -> install -> enable accessibility -> port forward -> readiness check.
    """

    def __init__(self, device_id: str | None = None):
        self._device_id = device_id
        self._client = CompanionClient()

    # ── ADB prefix helper ────────────────────────────────────────────

    def _adb(self) -> list[str]:
        if self._device_id:
            return ["adb", "-s", self._device_id]
        return ["adb"]

    def _run_adb(self, *args: str, timeout: int = 15) -> subprocess.CompletedProcess:
        return subprocess.run(
            [*self._adb(), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    # ── Queries ──────────────────────────────────────────────────────

    def is_installed(self) -> bool:
        """Check if the companion app is installed on the device."""
        result = self._run_adb("shell", "pm", "list", "packages")
        return COMPANION_PACKAGE in result.stdout

    def get_device_state(self) -> str:
        """Return the current ADB device state for the selected device."""
        result = self._run_adb("get-state")
        if result.returncode != 0:
            return (result.stderr or result.stdout).strip() or "disconnected"
        return result.stdout.strip() or "unknown"

    def is_device_connected(self) -> bool:
        """Return whether the selected ADB device is online."""
        return self.get_device_state() == "device"

    def get_installed_version(self) -> str | None:
        """Get the installed version name, or None if not installed."""
        result = self._run_adb(
            "shell", "dumpsys", "package", COMPANION_PACKAGE
        )
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith("versionName="):
                return line.split("=", 1)[1]
        return None

    def get_enabled_accessibility_services(self) -> str:
        """Return the raw enabled accessibility services setting value."""
        result = self._run_adb(
            "shell", "settings", "get", "secure",
            "enabled_accessibility_services",
        )
        return result.stdout.strip()

    def is_accessibility_globally_enabled(self) -> bool:
        """Check whether the Android accessibility master switch is enabled."""
        result = self._run_adb(
            "shell", "settings", "get", "secure", "accessibility_enabled"
        )
        return result.stdout.strip() == "1"

    def is_accessibility_service_enabled(self) -> bool:
        """Check whether the companion service is listed in secure settings."""
        return COMPANION_SERVICE in self.get_enabled_accessibility_services()

    def is_accessibility_enabled(self) -> bool:
        """Check whether accessibility is both globally enabled and includes this service."""
        return (
            self.is_accessibility_globally_enabled()
            and self.is_accessibility_service_enabled()
        )

    def get_accessibility_runtime_state(self) -> dict[str, bool]:
        """Read AccessibilityManager runtime state from dumpsys accessibility."""
        result = self._run_adb("shell", "dumpsys", "accessibility", timeout=20)
        state = {
            "service_enabled_in_manager": False,
            "service_bound": False,
            "service_crashed": False,
            "enabled_services_raw": "",
            "bound_services_raw": "",
            "crashed_services_raw": "",
        }
        for line in result.stdout.splitlines():
            stripped = line.strip()
            if stripped.startswith("Enabled services:"):
                raw = stripped.split(":", 1)[1].strip()
                state["enabled_services_raw"] = raw
                if COMPANION_SERVICE in raw:
                    state["service_enabled_in_manager"] = True
            elif stripped.startswith("Bound services:"):
                raw = stripped.split(":", 1)[1].strip()
                state["bound_services_raw"] = raw
                if (
                    COMPANION_SERVICE in raw
                    or COMPANION_PACKAGE in raw
                    or "Select to Speak" in raw
                ):
                    state["service_bound"] = True
            elif stripped.startswith("Crashed services:"):
                raw = stripped.split(":", 1)[1].strip()
                state["crashed_services_raw"] = raw
                if COMPANION_SERVICE in raw or COMPANION_PACKAGE in raw:
                    state["service_crashed"] = True
        return state

    def is_companion_process_running(self) -> bool:
        """Check whether the companion app process is running."""
        result = self._run_adb("shell", "pidof", COMPANION_PACKAGE)
        return result.returncode == 0 and bool(result.stdout.strip())

    def is_port_forwarded(self) -> bool:
        """Check if ADB port forwarding is active for the companion HTTP port."""
        result = self._run_adb("forward", "--list")
        expected_http = f"tcp:{COMPANION_HTTP_PORT}"
        expected_ws = f"tcp:{COMPANION_WS_PORT}"
        matched_http = False
        matched_ws = False
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) < 3:
                continue
            serial, local, remote = parts[:3]
            if self._device_id and serial != self._device_id:
                continue
            if local == expected_http and remote == expected_http:
                matched_http = True
            if local == expected_ws and remote == expected_ws:
                matched_ws = True
        return matched_http and matched_ws

    def _build_recommended_action(self, issues: list[str]) -> str | None:
        """Map the highest-priority issue to an actionable next step."""
        if not issues:
            return None

        first = issues[0]
        if "ADB" in first:
            return "请先确认 USB 调试已授权，并确保 `adb devices` 显示该设备为 device。"
        if "未安装" in first:
            return "运行 `phone-cli --instance adb companion-setup` 自动构建/安装辅助服务。"
        if "总开关" in first:
            return (
                "当前 ROM 没有真正打开无障碍总开关。"
                "请在手机上进入 设置 > 无障碍 > 已下载的应用 > Android 控制助手/Select to Speak 手动开启。"
            )
        if "crashed" in first:
            return "辅助服务已崩溃，请在手机上关闭后重新启用该无障碍服务，再重新执行 preflight。"
        if "启动异常" in first:
            return "辅助服务启动时发生异常，请查看 startup_error 并重新打开 Android 控制助手确认诊断信息。"
        if "未绑定" in first:
            return "服务设置已写入但系统没有真正绑定，请手动关闭再开启一次无障碍服务。"
        if "桥接" in first:
            return "运行 `phone-cli --instance adb companion-setup` 重新建立 ADB 端口转发。"
        if "未就绪" in first:
            return "打开手机上的 Android 控制助手页面，确认诊断页显示 service connected 后再重试。"
        return first

    # ── Build ────────────────────────────────────────────────────────

    def _check_build_prerequisites(self) -> list[str]:
        """Check for required build tools. Returns list of missing items."""
        missing = []

        # Check Android SDK
        android_home = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")
        if not android_home or not os.path.isdir(android_home):
            missing.append(
                "ANDROID_HOME or ANDROID_SDK_ROOT environment variable "
                "(must point to a valid Android SDK directory)"
            )

        # Check Java (gradle.properties may override, but system JAVA_HOME is fallback)
        java_home = os.environ.get("JAVA_HOME")
        if java_home and os.path.isdir(java_home):
            pass  # OK
        else:
            # Try to find java on PATH
            try:
                result = subprocess.run(
                    ["java", "-version"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                # Check for Java 17+
                version_line = result.stderr + result.stdout
                match = re.search(r'"(\d+)', version_line)
                if match:
                    major = int(match.group(1))
                    if major < 17:
                        missing.append(f"Java 17+ required (found Java {major})")
            except (FileNotFoundError, subprocess.TimeoutExpired):
                missing.append("Java 17+ (java command not found)")

        return missing

    def _build_apk(self) -> Path:
        """Build the companion APK from source."""
        gradlew = COMPANION_PROJECT_DIR / "gradlew"
        if not gradlew.exists():
            raise FileNotFoundError(
                f"android-companion project not found at {COMPANION_PROJECT_DIR}"
            )

        # Check prerequisites
        missing = self._check_build_prerequisites()
        if missing:
            raise EnvironmentError(
                "Cannot build companion APK. Missing prerequisites:\n"
                + "\n".join(f"  - {m}" for m in missing)
            )

        # Ensure gradlew is executable
        gradlew.chmod(0o755)

        # Build
        result = subprocess.run(
            [str(gradlew), "assembleDebug"],
            cwd=str(COMPANION_PROJECT_DIR),
            capture_output=True,
            text=True,
            timeout=180,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"Companion APK build failed (exit code {result.returncode}):\n"
                f"{result.stderr[-500:] if result.stderr else result.stdout[-500:]}"
            )

        if not APK_PATH.exists():
            raise FileNotFoundError(
                f"APK not found after build at {APK_PATH}"
            )

        return APK_PATH

    def _get_apk_path(self) -> Path:
        """Get the APK path, building from source if necessary."""
        if APK_PATH.exists():
            return APK_PATH
        return self._build_apk()

    # ── Install ──────────────────────────────────────────────────────

    def install(self) -> dict[str, Any]:
        """Install the companion APK on the device."""
        apk_path = self._get_apk_path()
        result = self._run_adb(
            "install", "-r", "-g", str(apk_path),
            timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"APK install failed: {result.stderr or result.stdout}"
            )
        return {"installed": True, "apk_path": str(apk_path)}

    # ── Enable accessibility ─────────────────────────────────────────

    def enable_accessibility(self) -> dict[str, Any]:
        """Enable the companion accessibility service on the device.

        NOTE: This method does NOT poll for service readiness (that requires
        port forwarding to be set up first). The caller (ensure_ready) handles
        readiness polling after port forwarding is established.
        """
        # Read current enabled services
        result = self._run_adb(
            "shell", "settings", "get", "secure",
            "enabled_accessibility_services",
        )
        current = result.stdout.strip()
        if current in ("null", ""):
            new_value = COMPANION_SERVICE
        elif COMPANION_SERVICE in current:
            new_value = current  # Already present
        else:
            new_value = f"{current}:{COMPANION_SERVICE}"

        # Set the accessibility services
        self._run_adb(
            "shell", "settings", "put", "secure",
            "enabled_accessibility_services", new_value,
        )

        # Also ensure accessibility is globally enabled
        self._run_adb(
            "shell", "settings", "put", "secure",
            "accessibility_enabled", "1",
        )

        # Launch MainActivity to initialize the service
        self._run_adb(
            "shell", "am", "start", "-n", COMPANION_MAIN_ACTIVITY,
        )

        # Give the system a moment to bind the service and refresh diagnostics.
        time.sleep(2)
        status = self.get_status()
        if status.get("accessibility_enabled") and status.get("accessibility_service_bound"):
            return {"enabled": True}

        issues = status.get("issues", [])
        return {
            "enabled": False,
            "service_ready": bool(status.get("service_ready")),
            "diagnostics": status,
            "message": self._build_recommended_action(issues)
            or (
                "Failed to enable accessibility service programmatically. "
                "Some OEM ROMs (Xiaomi/OPPO/Vivo) block this. "
                "Please enable manually: Settings > Accessibility > Select to Speak > ON"
            ),
        }

    # ── Port forwarding ──────────────────────────────────────────────

    def setup_port_forward(self) -> dict[str, Any]:
        """Set up ADB port forwarding for the companion HTTP and WS ports."""
        http_result = self._run_adb(
            "forward", f"tcp:{COMPANION_HTTP_PORT}", f"tcp:{COMPANION_HTTP_PORT}",
        )
        if http_result.returncode != 0:
            raise RuntimeError(
                f"ADB port forward failed for HTTP port {COMPANION_HTTP_PORT}: "
                f"{http_result.stderr or http_result.stdout}"
            )
        ws_result = self._run_adb(
            "forward", f"tcp:{COMPANION_WS_PORT}", f"tcp:{COMPANION_WS_PORT}",
        )
        if ws_result.returncode != 0:
            raise RuntimeError(
                f"ADB port forward failed for WS port {COMPANION_WS_PORT}: "
                f"{ws_result.stderr or ws_result.stdout}"
            )
        return {"forwarded": True, "http_port": COMPANION_HTTP_PORT, "ws_port": COMPANION_WS_PORT}

    # ── Full lifecycle: ensure_ready() ───────────────────────────────

    def ensure_ready(self) -> dict[str, Any]:
        """Complete decision chain to make the companion service usable.

        Flow:
        1. Check installed → install if needed (build from source if no APK)
        2. Check accessibility enabled → enable if needed
        3. Check port forwarding → set up if needed (before readiness polling!)
        4. Check service readiness → launch MainActivity and retry if needed
        """
        result: dict[str, Any] = {
            "available": False,
            "steps": [],
        }

        adb_state = self.get_device_state()
        if adb_state != "device":
            result["error"] = (
                f"ADB connection is not ready for {self._device_id or 'current device'}: {adb_state}"
            )
            result["steps"].append({"adb": {"connected": False, "state": adb_state}})
            return result

        result["steps"].append({"adb": {"connected": True, "state": adb_state}})

        # Step 1: Install
        if not self.is_installed():
            try:
                install_result = self.install()
                result["steps"].append({"install": install_result})
            except (FileNotFoundError, EnvironmentError, RuntimeError) as e:
                result["error"] = str(e)
                result["steps"].append({"install": {"error": str(e)}})
                return result
        else:
            result["steps"].append({"install": "already_installed"})

        # Step 2: Enable accessibility (does NOT poll readiness — needs port forward first)
        if not self.is_accessibility_enabled():
            enable_result = self.enable_accessibility()
            result["steps"].append({"accessibility": enable_result})
            if not enable_result.get("enabled"):
                result["error"] = enable_result.get("message", "Failed to enable accessibility")
                return result
        else:
            result["steps"].append({"accessibility": "already_enabled"})

        accessibility_status = self.get_status()
        if accessibility_status.get("issues"):
            blocking_issues = [
                issue for issue in accessibility_status["issues"]
                if "桥接" not in issue and "未就绪" not in issue
            ]
            if blocking_issues:
                result["steps"].append({
                    "accessibility_runtime": {
                        "bound": accessibility_status.get("accessibility_service_bound"),
                        "crashed": accessibility_status.get("accessibility_service_crashed"),
                        "issues": blocking_issues,
                    }
                })
                result["error"] = self._build_recommended_action(blocking_issues) or blocking_issues[0]
                return result

        # Step 3: Port forwarding (must happen BEFORE readiness polling)
        if not self.is_port_forwarded():
            try:
                fwd_result = self.setup_port_forward()
                result["steps"].append({"port_forward": fwd_result})
            except RuntimeError as e:
                result["error"] = str(e)
                result["steps"].append({"port_forward": {"error": str(e)}})
                return result
        else:
            result["steps"].append({"port_forward": "already_forwarded"})

        # Step 4: Service readiness (now port forwarding is guaranteed)
        if self._client.is_ready():
            result["available"] = True
            result["steps"].append({"ready": True})
            return result

        # Try launching MainActivity to wake up the service
        self._run_adb(
            "shell", "am", "start", "-n", COMPANION_MAIN_ACTIVITY,
        )

        for _ in range(5):
            time.sleep(1)
            if self._client.is_ready():
                result["available"] = True
                result["steps"].append({"ready": True})
                return result

        status = self.get_status()
        result["steps"].append({"ready": {"ok": False, "issues": status.get("issues", [])}})
        result["error"] = self._build_recommended_action(status.get("issues", [])) or (
            "Companion service not ready after launch attempt"
        )
        return result

    # ── Status query ─────────────────────────────────────────────────

    def get_status(self) -> dict[str, Any]:
        """Get a comprehensive status report of the companion."""
        adb_state = self.get_device_state()
        device_connected = adb_state == "device"

        installed = self.is_installed() if device_connected else False
        version = self.get_installed_version() if installed else None
        accessibility_global_enabled = (
            self.is_accessibility_globally_enabled() if installed else False
        )
        accessibility_service_enabled = (
            self.is_accessibility_service_enabled() if installed else False
        )
        accessibility_enabled = (
            accessibility_global_enabled and accessibility_service_enabled
        )
        runtime_state = self.get_accessibility_runtime_state() if installed else {
            "service_enabled_in_manager": False,
            "service_bound": False,
            "service_crashed": False,
            "enabled_services_raw": "",
            "bound_services_raw": "",
            "crashed_services_raw": "",
        }
        companion_process_running = self.is_companion_process_running() if installed else False
        port_forwarded = self.is_port_forwarded() if device_connected else False

        service_ready = False
        service_status: dict[str, Any] | None = None
        runtime_service_connected = False
        snapshot_available = False
        http_server_running = False
        web_socket_server_running = False
        startup_error: str | None = None
        if port_forwarded:
            try:
                service_status = self._client.get_status()
                service_ready = bool(service_status.get("ready"))
                runtime_service_connected = bool(service_status.get("serviceConnected"))
                snapshot_available = bool(
                    service_status.get("snapshotAvailable", service_status.get("ready"))
                )
                http_server_running = bool(
                    service_status.get("httpServerRunning", service_ready)
                )
                web_socket_server_running = bool(
                    service_status.get("webSocketServerRunning", service_ready)
                )
                startup_error = service_status.get("startupError")
            except CompanionUnavailableError:
                pass

        accessibility_service_bound = (
            runtime_state["service_bound"] or runtime_service_connected
        )
        diagnostic_notes: list[str] = []
        if runtime_service_connected and not runtime_state["service_bound"]:
            diagnostic_notes.append(
                "dumpsys accessibility 未显示 Bound services，但 companion /status 返回 serviceConnected=true，已按运行态判定为健康。"
            )

        issues: list[str] = []
        issue_codes: list[str] = []
        if not device_connected:
            issues.append(f"ADB 连接异常: {adb_state}")
            issue_codes.append("ADB_DISCONNECTED")
        elif not installed:
            issues.append("辅助服务 APK 未安装")
            issue_codes.append("APK_NOT_INSTALLED")
        else:
            if not accessibility_global_enabled:
                issues.append("Android 无障碍总开关仍为关闭状态")
                issue_codes.append("ACCESSIBILITY_DISABLED")
            if not accessibility_service_enabled:
                issues.append("辅助服务未写入 enabled_accessibility_services")
                issue_codes.append("SERVICE_NOT_ENABLED")
            if runtime_state["service_crashed"]:
                issues.append("辅助服务已被系统标记为 crashed")
                issue_codes.append("SERVICE_CRASHED")
            if startup_error:
                issues.append(f"辅助服务启动异常: {startup_error}")
                issue_codes.append("SERVICE_STARTUP_ERROR")
            if accessibility_enabled and not accessibility_service_bound:
                issues.append("辅助服务未绑定到 AccessibilityManager")
                issue_codes.append("SERVICE_NOT_BOUND")
            if accessibility_enabled and not port_forwarded:
                issues.append("ADB 桥接未建立")
                issue_codes.append("PORT_FORWARD_MISSING")
            if port_forwarded and not http_server_running:
                issues.append("Companion HTTP 服务未运行")
                issue_codes.append("HTTP_SERVER_DOWN")
            if port_forwarded and not web_socket_server_running:
                issues.append("Companion WebSocket 服务未运行")
                issue_codes.append("WEBSOCKET_SERVER_DOWN")
            if port_forwarded and runtime_service_connected and not snapshot_available:
                issues.append("Companion 尚未采集到有效快照")
                issue_codes.append("SNAPSHOT_UNAVAILABLE")
            if port_forwarded and not service_ready:
                issues.append("Companion HTTP 服务未就绪")
                issue_codes.append("HTTP_NOT_READY")

        ready = (
            device_connected
            and installed
            and accessibility_enabled
            and accessibility_service_bound
            and not runtime_state["service_crashed"]
            and port_forwarded
            and http_server_running
            and web_socket_server_running
            and service_ready
        )

        return {
            "device_id": self._device_id,
            "device_connected": device_connected,
            "adb_state": adb_state,
            "installed": installed,
            "version": version,
            "accessibility_enabled": accessibility_enabled,
            "accessibility_global_enabled": accessibility_global_enabled,
            "accessibility_service_enabled": accessibility_service_enabled,
            "accessibility_service_bound": accessibility_service_bound,
            "accessibility_service_bound_raw": runtime_state["service_bound"],
            "accessibility_service_crashed": runtime_state["service_crashed"],
            "enabled_accessibility_services": self.get_enabled_accessibility_services() if installed else "",
            "dumpsys_enabled_services": runtime_state.get("enabled_services_raw", ""),
            "dumpsys_bound_services": runtime_state.get("bound_services_raw", ""),
            "dumpsys_crashed_services": runtime_state.get("crashed_services_raw", ""),
            "companion_process_running": companion_process_running,
            "port_forwarded": port_forwarded,
            "service_ready": service_ready,
            "runtime_service_connected": runtime_service_connected,
            "snapshot_available": snapshot_available,
            "http_server_running": http_server_running,
            "web_socket_server_running": web_socket_server_running,
            "startup_error": startup_error,
            "service_status": service_status,
            "ready": ready,
            "issue_codes": issue_codes,
            "issues": issues,
            "diagnostic_notes": diagnostic_notes,
            "recommended_action": self._build_recommended_action(issues),
        }
