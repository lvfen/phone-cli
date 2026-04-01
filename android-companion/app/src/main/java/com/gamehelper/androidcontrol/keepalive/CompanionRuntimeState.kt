package com.gamehelper.androidcontrol.keepalive

object CompanionRuntimeState {
    @Volatile
    var serviceConnected: Boolean = false

    @Volatile
    var httpServerRunning: Boolean = false

    @Volatile
    var webSocketServerRunning: Boolean = false

    @Volatile
    var startupError: String? = null

    @Volatile
    var lastCaptureAt: String? = null

    @Volatile
    var activePackageName: String? = null

    @Volatile
    var overlayVisible: Boolean = false

    @Volatile
    var overlayPermissionGranted: Boolean = false
}
