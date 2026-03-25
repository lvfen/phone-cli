package com.gamehelper.androidcontrol.keepalive

data class DiagnosticInput(
    val accessibilityEnabled: Boolean,
    val serviceEnabled: Boolean,
    val serviceConnected: Boolean,
    val foregroundServiceEnabled: Boolean,
    val ignoringBatteryOptimizations: Boolean,
    val httpPortReachable: Boolean,
    val webSocketPortReachable: Boolean,
    val lastCaptureAt: String? = null,
    val activePackageName: String? = null
)

data class DiagnosticSnapshot(
    val accessibilityEnabled: Boolean,
    val serviceEnabled: Boolean,
    val serviceConnected: Boolean,
    val foregroundServiceEnabled: Boolean,
    val ignoringBatteryOptimizations: Boolean,
    val httpPortReachable: Boolean,
    val webSocketPortReachable: Boolean,
    val lastCaptureAt: String?,
    val activePackageName: String?,
    val companionReady: Boolean,
    val primaryIssue: String
)

class ServiceHealthMonitor {

    fun evaluate(input: DiagnosticInput): DiagnosticSnapshot {
        val ready = input.accessibilityEnabled &&
            input.serviceEnabled &&
            input.serviceConnected &&
            input.httpPortReachable &&
            input.webSocketPortReachable

        val primaryIssue = when {
            !input.accessibilityEnabled -> "请先打开系统无障碍总开关。"
            !input.serviceEnabled -> "请启用 Select to Speak 无障碍服务。"
            !input.serviceConnected -> "无障碍服务未连接，请重新启用。"
            !input.httpPortReachable || !input.webSocketPortReachable -> "本地桥接异常，请重启辅助服务。"
            !input.foregroundServiceEnabled || !input.ignoringBatteryOptimizations -> "保活配置未完成。"
            else -> "助手就绪。"
        }

        return DiagnosticSnapshot(
            accessibilityEnabled = input.accessibilityEnabled,
            serviceEnabled = input.serviceEnabled,
            serviceConnected = input.serviceConnected,
            foregroundServiceEnabled = input.foregroundServiceEnabled,
            ignoringBatteryOptimizations = input.ignoringBatteryOptimizations,
            httpPortReachable = input.httpPortReachable,
            webSocketPortReachable = input.webSocketPortReachable,
            lastCaptureAt = input.lastCaptureAt,
            activePackageName = input.activePackageName,
            companionReady = ready,
            primaryIssue = primaryIssue
        )
    }

    fun notificationStatus(snapshot: DiagnosticSnapshot): String {
        return when {
            snapshot.companionReady && !snapshot.activePackageName.isNullOrBlank() -> {
                "已连接：${snapshot.activePackageName}"
            }
            !snapshot.foregroundServiceEnabled || !snapshot.ignoringBatteryOptimizations -> {
                "保活配置未完成"
            }
            else -> snapshot.primaryIssue.removeSuffix("。")
        }
    }
}
