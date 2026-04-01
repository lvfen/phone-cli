package com.gamehelper.androidcontrol.keepalive

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ServiceHealthMonitorTest {

    private val monitor = ServiceHealthMonitor()

    @Test
    fun evaluateFlagsCompanionAsNotReadyWhenGlobalAccessibilityIsDisabled() {
        val snapshot = monitor.evaluate(
            DiagnosticInput(
                accessibilityEnabled = false,
                serviceEnabled = true,
                serviceConnected = false,
                foregroundServiceEnabled = false,
                ignoringBatteryOptimizations = false,
                httpPortReachable = false,
                webSocketPortReachable = false,
                overlayEnabled = false,
                overlayPermissionGranted = false,
                overlayVisible = false
            )
        )

        assertFalse(snapshot.companionReady)
        assertEquals("请先打开系统无障碍总开关。", snapshot.primaryIssue)
    }

    @Test
    fun evaluateMarksCompanionReadyWhenAllHealthSignalsAreGreen() {
        val snapshot = monitor.evaluate(
            DiagnosticInput(
                accessibilityEnabled = true,
                serviceEnabled = true,
                serviceConnected = true,
                foregroundServiceEnabled = true,
                ignoringBatteryOptimizations = true,
                httpPortReachable = true,
                webSocketPortReachable = true,
                overlayEnabled = true,
                overlayPermissionGranted = true,
                overlayVisible = true,
                lastCaptureAt = "2026-03-20T10:02:06Z",
                activePackageName = "com.android.settings"
            )
        )

        assertTrue(snapshot.companionReady)
        assertEquals("助手就绪。", snapshot.primaryIssue)
        assertEquals("已连接：com.android.settings", monitor.notificationStatus(snapshot))
    }

    @Test
    fun notificationStatusExplainsWhyKeepAliveIsDegraded() {
        val snapshot = monitor.evaluate(
            DiagnosticInput(
                accessibilityEnabled = true,
                serviceEnabled = true,
                serviceConnected = true,
                foregroundServiceEnabled = false,
                ignoringBatteryOptimizations = false,
                httpPortReachable = true,
                webSocketPortReachable = false,
                overlayEnabled = false,
                overlayPermissionGranted = false,
                overlayVisible = false
            )
        )

        assertEquals("保活配置未完成", monitor.notificationStatus(snapshot))
    }

    @Test
    fun evaluateProvidesDetailedReasonsForLocalBridgeIssue() {
        val snapshot = monitor.evaluate(
            DiagnosticInput(
                accessibilityEnabled = true,
                serviceEnabled = true,
                serviceConnected = true,
                foregroundServiceEnabled = true,
                ignoringBatteryOptimizations = true,
                httpPortReachable = false,
                webSocketPortReachable = true,
                overlayEnabled = false,
                overlayPermissionGranted = false,
                overlayVisible = false,
            )
        )

        assertEquals("LOCAL_SERVER_UNREACHABLE", snapshot.issueCode)
        assertTrue(snapshot.details.contains("HTTP 端口 17342 未监听"))
    }

    @Test
    fun evaluateReportsOverlayIssueWhenOverlayEnabledButHidden() {
        val snapshot = monitor.evaluate(
            DiagnosticInput(
                accessibilityEnabled = true,
                serviceEnabled = true,
                serviceConnected = true,
                foregroundServiceEnabled = true,
                ignoringBatteryOptimizations = true,
                httpPortReachable = true,
                webSocketPortReachable = true,
                overlayEnabled = true,
                overlayPermissionGranted = true,
                overlayVisible = false,
            )
        )

        assertEquals("OVERLAY_INCOMPLETE", snapshot.issueCode)
        assertEquals("悬浮窗异常", monitor.notificationStatus(snapshot))
        assertTrue(snapshot.details.contains("悬浮窗未显示，可能被系统回收"))
    }
}
