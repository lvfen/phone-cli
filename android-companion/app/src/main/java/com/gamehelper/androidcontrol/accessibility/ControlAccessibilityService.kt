package com.gamehelper.androidcontrol.accessibility

import android.accessibilityservice.AccessibilityService
import android.view.accessibility.AccessibilityEvent
import com.gamehelper.androidcontrol.actions.GestureExecutor
import com.gamehelper.androidcontrol.actions.NodeActionExecutor
import com.gamehelper.androidcontrol.capture.HierarchyCaptureManager
import com.gamehelper.androidcontrol.foreground.CompanionForegroundService
import com.gamehelper.androidcontrol.keepalive.CompanionDiagnosticReader
import com.gamehelper.androidcontrol.keepalive.CompanionRuntimeState
import com.gamehelper.androidcontrol.model.CompanionStatusDto
import com.gamehelper.androidcontrol.server.CompanionHttpServer
import com.gamehelper.androidcontrol.server.CompanionWebSocketServer
import com.gamehelper.androidcontrol.store.SnapshotStore

open class ControlAccessibilityService : AccessibilityService() {

    private val snapshotStore = SnapshotStore()
    private lateinit var captureManager: HierarchyCaptureManager
    private lateinit var gestureExecutor: GestureExecutor
    private lateinit var nodeActionExecutor: NodeActionExecutor
    private lateinit var webSocketServer: CompanionWebSocketServer
    private lateinit var httpServer: CompanionHttpServer

    override fun onServiceConnected() {
        super.onServiceConnected()
        instance = this
        CompanionRuntimeState.serviceConnected = true

        captureManager = HierarchyCaptureManager(this, snapshotStore)
        gestureExecutor = GestureExecutor(this)
        nodeActionExecutor = NodeActionExecutor(captureManager, gestureExecutor)
        webSocketServer = CompanionWebSocketServer(port = 17343)
        httpServer = CompanionHttpServer(
            port = 17342,
            snapshotStore = snapshotStore,
            captureManager = captureManager,
            nodeActionExecutor = nodeActionExecutor,
            gestureExecutor = gestureExecutor,
            statusProvider = ::buildStatus,
            webSocketServer = webSocketServer
        )

        webSocketServer.start()
        httpServer.start()
        captureManager.captureLatest()?.also(::updateRuntimeState)

        if (CompanionDiagnosticReader(this).isForegroundKeepAliveEnabled()) {
            CompanionForegroundService.start(this)
        }
    }

    @Volatile
    private var lastEventCaptureMs = 0L

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        if (event == null) return
        val now = System.currentTimeMillis()
        if (now - lastEventCaptureMs < 200) return
        lastEventCaptureMs = now
        val snapshot = captureManager.captureLatest() ?: return
        updateRuntimeState(snapshot)
        runCatching { webSocketServer.broadcastSnapshot(snapshot) }
    }

    override fun onInterrupt() = Unit

    override fun onDestroy() {
        runCatching { httpServer.stop() }
        runCatching { webSocketServer.stop() }
        CompanionRuntimeState.serviceConnected = false
        CompanionRuntimeState.lastCaptureAt = null
        CompanionRuntimeState.activePackageName = null
        instance = null
        super.onDestroy()
    }

    private fun buildStatus(): CompanionStatusDto {
        val snapshot = snapshotStore.getSnapshot()
        return CompanionStatusDto(
            ready = snapshot != null,
            serviceConnected = CompanionRuntimeState.serviceConnected,
            lastCaptureAt = snapshot?.capturedAt,
            packageName = snapshot?.packageName
        )
    }

    private fun updateRuntimeState(snapshot: com.gamehelper.androidcontrol.model.UiSnapshotDto) {
        CompanionRuntimeState.serviceConnected = true
        CompanionRuntimeState.lastCaptureAt = snapshot.capturedAt
        CompanionRuntimeState.activePackageName = snapshot.packageName
    }

    companion object {
        @Volatile
        var instance: ControlAccessibilityService? = null
            private set
    }
}
