package com.gamehelper.androidcontrol.keepalive

data class DiagnosticInput(
    val accessibilityEnabled: Boolean,
    val serviceEnabled: Boolean,
    val serviceConnected: Boolean,
    val foregroundServiceEnabled: Boolean,
    val ignoringBatteryOptimizations: Boolean,
    val httpPortReachable: Boolean,
    val webSocketPortReachable: Boolean,
    val overlayEnabled: Boolean,
    val overlayPermissionGranted: Boolean,
    val overlayVisible: Boolean,
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
    val overlayEnabled: Boolean,
    val overlayPermissionGranted: Boolean,
    val overlayVisible: Boolean,
    val lastCaptureAt: String?,
    val activePackageName: String?,
    val companionReady: Boolean,
    val primaryIssue: String,
    val issueCode: String,
    val details: List<String>
)

class ServiceHealthMonitor {

    fun evaluate(input: DiagnosticInput): DiagnosticSnapshot {
        val ready = input.accessibilityEnabled &&
            input.serviceEnabled &&
            input.serviceConnected &&
            input.httpPortReachable &&
            input.webSocketPortReachable

        val overlayHealthy = !input.overlayEnabled ||
            (input.overlayPermissionGranted && input.overlayVisible)

        val details = buildList {
            if (!input.accessibilityEnabled) add("系统无障碍总开关关闭")
            if (!input.serviceEnabled) add("辅助服务未出现在已启用服务列表中")
            if (!input.serviceConnected) add("AccessibilityService 尚未与系统建立运行态连接")
            if (!input.httpPortReachable) add("HTTP 端口 17342 未监听")
            if (!input.webSocketPortReachable) add("WebSocket 端口 17343 未监听")
            if (!input.foregroundServiceEnabled) add("常驻通知保活未开启")
            if (!input.ignoringBatteryOptimizations) add("未加入电池优化白名单")
            if (input.overlayEnabled && !input.overlayPermissionGranted) add("悬浮窗权限未授权")
            if (input.overlayEnabled && input.overlayPermissionGranted && !input.overlayVisible) add("悬浮窗未显示，可能被系统回收")
        }

        val issueCode = when {
            !input.accessibilityEnabled -> "ACCESSIBILITY_DISABLED"
            !input.serviceEnabled -> "SERVICE_NOT_ENABLED"
            !input.serviceConnected -> "SERVICE_NOT_CONNECTED"
            !input.httpPortReachable || !input.webSocketPortReachable -> "LOCAL_SERVER_UNREACHABLE"
            !overlayHealthy -> "OVERLAY_INCOMPLETE"
            !input.foregroundServiceEnabled || !input.ignoringBatteryOptimizations -> "KEEPALIVE_INCOMPLETE"
            else -> "READY"
        }

        val primaryIssue = when (issueCode) {
            "ACCESSIBILITY_DISABLED" -> "请先打开系统无障碍总开关。"
            "SERVICE_NOT_ENABLED" -> "请启用 Select to Speak 无障碍服务。"
            "SERVICE_NOT_CONNECTED" -> "无障碍服务未连接，请重新启用。"
            "LOCAL_SERVER_UNREACHABLE" -> "本地桥接异常，请重启辅助服务。"
            "OVERLAY_INCOMPLETE" -> "悬浮窗保活未生效，请检查权限或显示状态。"
            "KEEPALIVE_INCOMPLETE" -> "保活配置未完成。"
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
            overlayEnabled = input.overlayEnabled,
            overlayPermissionGranted = input.overlayPermissionGranted,
            overlayVisible = input.overlayVisible,
            lastCaptureAt = input.lastCaptureAt,
            activePackageName = input.activePackageName,
            companionReady = ready,
            primaryIssue = primaryIssue,
            issueCode = issueCode,
            details = details
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
            snapshot.overlayEnabled && (!snapshot.overlayPermissionGranted || !snapshot.overlayVisible) -> {
                "悬浮窗异常"
            }
            else -> snapshot.primaryIssue.removeSuffix("。")
        }
    }
}
