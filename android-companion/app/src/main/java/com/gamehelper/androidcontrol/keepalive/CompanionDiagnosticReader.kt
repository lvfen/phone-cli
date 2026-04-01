package com.gamehelper.androidcontrol.keepalive

import android.content.ComponentName
import android.content.Context
import android.provider.Settings
import java.net.InetSocketAddress
import java.net.Socket

class CompanionDiagnosticReader(
    private val context: Context,
    private val monitor: ServiceHealthMonitor = ServiceHealthMonitor(),
    private val batteryOptimizationHelper: BatteryOptimizationHelper = BatteryOptimizationHelper(context),
    private val overlayPermissionHelper: OverlayPermissionHelper = OverlayPermissionHelper(context)
) {

    fun snapshot(): DiagnosticSnapshot {
        val httpReachable = CompanionRuntimeState.httpServerRunning || isLoopbackPortReachable(17342)
        val webSocketReachable = CompanionRuntimeState.webSocketServerRunning || isLoopbackPortReachable(17343)
        val overlayPermissionGranted = overlayPermissionHelper.canDrawOverlays()
        CompanionRuntimeState.overlayPermissionGranted = overlayPermissionGranted

        return monitor.evaluate(
            DiagnosticInput(
                accessibilityEnabled = isAccessibilityEnabled(),
                serviceEnabled = isServiceEnabled(),
                serviceConnected = CompanionRuntimeState.serviceConnected,
                foregroundServiceEnabled = isForegroundKeepAliveEnabled(),
                ignoringBatteryOptimizations = batteryOptimizationHelper.isIgnoringBatteryOptimizations(),
                httpPortReachable = httpReachable,
                webSocketPortReachable = webSocketReachable,
                overlayEnabled = isOverlayEnabled(),
                overlayPermissionGranted = overlayPermissionGranted,
                overlayVisible = CompanionRuntimeState.overlayVisible,
                lastCaptureAt = CompanionRuntimeState.lastCaptureAt,
                activePackageName = CompanionRuntimeState.activePackageName
            )
        )
    }

    fun isForegroundKeepAliveEnabled(): Boolean {
        return context.getSharedPreferences(KeepAlivePreferences.NAME, Context.MODE_PRIVATE)
            .getBoolean(KeepAlivePreferences.KEY_FOREGROUND_SERVICE_ENABLED, false)
    }

    fun setForegroundKeepAliveEnabled(enabled: Boolean) {
        context.getSharedPreferences(KeepAlivePreferences.NAME, Context.MODE_PRIVATE)
            .edit()
            .putBoolean(KeepAlivePreferences.KEY_FOREGROUND_SERVICE_ENABLED, enabled)
            .apply()
    }

    fun isOverlayEnabled(): Boolean {
        return context.getSharedPreferences(KeepAlivePreferences.NAME, Context.MODE_PRIVATE)
            .getBoolean(KeepAlivePreferences.KEY_OVERLAY_ENABLED, false)
    }

    fun setOverlayEnabled(enabled: Boolean) {
        context.getSharedPreferences(KeepAlivePreferences.NAME, Context.MODE_PRIVATE)
            .edit()
            .putBoolean(KeepAlivePreferences.KEY_OVERLAY_ENABLED, enabled)
            .apply()
    }

    fun loadOverlayPosition(): Pair<Int, Int>? {
        val preferences = context.getSharedPreferences(KeepAlivePreferences.NAME, Context.MODE_PRIVATE)
        if (!preferences.contains(KeepAlivePreferences.KEY_OVERLAY_X) ||
            !preferences.contains(KeepAlivePreferences.KEY_OVERLAY_Y)
        ) {
            return null
        }
        return preferences.getInt(KeepAlivePreferences.KEY_OVERLAY_X, 0) to
            preferences.getInt(KeepAlivePreferences.KEY_OVERLAY_Y, 0)
    }

    fun saveOverlayPosition(x: Int, y: Int) {
        context.getSharedPreferences(KeepAlivePreferences.NAME, Context.MODE_PRIVATE)
            .edit()
            .putInt(KeepAlivePreferences.KEY_OVERLAY_X, x)
            .putInt(KeepAlivePreferences.KEY_OVERLAY_Y, y)
            .apply()
    }

    private fun isAccessibilityEnabled(): Boolean {
        return Settings.Secure.getInt(
            context.contentResolver,
            Settings.Secure.ACCESSIBILITY_ENABLED,
            0
        ) == 1
    }

    private fun isServiceEnabled(): Boolean {
        val enabledServices = Settings.Secure.getString(
            context.contentResolver,
            Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES
        ).orEmpty()

        val componentName = ComponentName(
            context.packageName,
            "com.google.android.accessibility.selecttospeak.SelectToSpeakService"
        ).flattenToString()

        return enabledServices.split(':').contains(componentName)
    }

    private fun isLoopbackPortReachable(port: Int): Boolean {
        return runCatching {
            Socket().use { socket ->
                socket.connect(InetSocketAddress("127.0.0.1", port), 250)
            }
        }.isSuccess
    }
}
