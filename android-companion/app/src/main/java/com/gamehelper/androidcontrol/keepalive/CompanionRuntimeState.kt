package com.gamehelper.androidcontrol.keepalive

object CompanionRuntimeState {
    @Volatile
    var serviceConnected: Boolean = false

    @Volatile
    var lastCaptureAt: String? = null

    @Volatile
    var activePackageName: String? = null
}
