package com.gamehelper.androidcontrol.receiver

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.gamehelper.androidcontrol.foreground.CompanionForegroundService
import com.gamehelper.androidcontrol.keepalive.CompanionDiagnosticReader

class BootReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        if (!SUPPORTED_ACTIONS.contains(intent.action)) return

        val diagnosticReader = CompanionDiagnosticReader(context)
        if (diagnosticReader.isForegroundKeepAliveEnabled()) {
            CompanionForegroundService.start(context)
        }
    }

    companion object {
        private val SUPPORTED_ACTIONS = setOf(
            Intent.ACTION_BOOT_COMPLETED,
            Intent.ACTION_MY_PACKAGE_REPLACED,
            Intent.ACTION_LOCKED_BOOT_COMPLETED
        )
    }
}
