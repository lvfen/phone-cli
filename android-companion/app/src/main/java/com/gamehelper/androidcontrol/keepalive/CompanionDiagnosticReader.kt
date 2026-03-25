package com.gamehelper.androidcontrol.keepalive

import android.content.ComponentName
import android.content.Context
import android.provider.Settings
import java.net.InetSocketAddress
import java.net.Socket

class CompanionDiagnosticReader(
    private val context: Context,
    private val monitor: ServiceHealthMonitor = ServiceHealthMonitor(),
    private val batteryOptimizationHelper: BatteryOptimizationHelper = BatteryOptimizationHelper(context)
) {

    fun snapshot(): DiagnosticSnapshot {
        return monitor.evaluate(
            DiagnosticInput(
                accessibilityEnabled = isAccessibilityEnabled(),
                serviceEnabled = isServiceEnabled(),
                serviceConnected = CompanionRuntimeState.serviceConnected,
                foregroundServiceEnabled = isForegroundKeepAliveEnabled(),
                ignoringBatteryOptimizations = batteryOptimizationHelper.isIgnoringBatteryOptimizations(),
                httpPortReachable = isLoopbackPortReachable(17342),
                webSocketPortReachable = isLoopbackPortReachable(17343),
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
