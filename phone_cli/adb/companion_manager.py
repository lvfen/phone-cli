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

    def is_accessibility_enabled(self) -> bool:
        """Check if the companion accessibility service is enabled."""
        result = self._run_adb(
            "shell", "settings", "get", "secure",
            "enabled_accessibility_services",
        )
        return COMPANION_SERVICE in result.stdout

    def is_port_forwarded(self) -> bool:
        """Check if ADB port forwarding is active for the companion HTTP port."""
        result = self._run_adb("forward", "--list")
        return f"tcp:{COMPANION_HTTP_PORT}" in result.stdout

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

        # Check if at least the accessibility setting took effect
        time.sleep(2)
        if self.is_accessibility_enabled():
            return {"enabled": True}

        return {
            "enabled": False,
            "service_ready": False,
            "message": "Failed to enable accessibility service programmatically. "
                       "Some OEM ROMs (Xiaomi/OPPO/Vivo) block this. "
                       "Please enable manually: Settings > Accessibility > Select to Speak > ON",
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

        result["steps"].append({"ready": False})
        result["error"] = "Companion service not ready after launch attempt"
        return result

    # ── Status query ─────────────────────────────────────────────────

    def get_status(self) -> dict[str, Any]:
        """Get a comprehensive status report of the companion."""
        installed = self.is_installed()
        version = self.get_installed_version() if installed else None
        accessibility_enabled = self.is_accessibility_enabled() if installed else False
        port_forwarded = self.is_port_forwarded()

        service_ready = False
        service_status: dict[str, Any] | None = None
        if port_forwarded:
            try:
                service_status = self._client.get_status()
                service_ready = bool(service_status.get("ready"))
            except CompanionUnavailableError:
                pass

        return {
            "installed": installed,
            "version": version,
            "accessibility_enabled": accessibility_enabled,
            "port_forwarded": port_forwarded,
            "service_ready": service_ready,
            "service_status": service_status,
        }
