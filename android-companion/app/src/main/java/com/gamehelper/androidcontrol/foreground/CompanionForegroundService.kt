package com.gamehelper.androidcontrol.foreground

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import com.gamehelper.androidcontrol.MainActivity
import com.gamehelper.androidcontrol.R
import com.gamehelper.androidcontrol.keepalive.CompanionDiagnosticReader

class CompanionForegroundService : Service() {

    private val handler = Handler(Looper.getMainLooper())
    private val diagnosticReader by lazy { CompanionDiagnosticReader(this) }
    private val refreshRunnable = object : Runnable {
        override fun run() {
            updateNotification()
            handler.postDelayed(this, REFRESH_INTERVAL_MS)
        }
    }

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(
                NOTIFICATION_ID,
                buildNotification(),
                ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC
            )
        } else {
            startForeground(NOTIFICATION_ID, buildNotification())
        }
        handler.post(refreshRunnable)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_STOP -> {
                diagnosticReader.setForegroundKeepAliveEnabled(false)
                stopSelf()
            }

            else -> updateNotification()
        }
        return START_STICKY
    }

    override fun onDestroy() {
        handler.removeCallbacks(refreshRunnable)
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun updateNotification() {
        val manager = getSystemService(NotificationManager::class.java)
        manager.notify(NOTIFICATION_ID, buildNotification())
    }

    private fun buildNotification() = NotificationCompat.Builder(this, CHANNEL_ID)
        .setSmallIcon(android.R.drawable.stat_notify_sync)
        .setOngoing(true)
        .setOnlyAlertOnce(true)
        .setContentTitle(getString(R.string.keepalive_notification_title))
        .setContentText(
            diagnosticReader.run {
                val snapshot = snapshot()
                ServiceText.formatStatusLine(snapshot.primaryIssue, snapshot.activePackageName)
            }
        )
        .setStyle(
            NotificationCompat.BigTextStyle().bigText(
                diagnosticReader.run {
                    val snapshot = snapshot()
                    val detail = ServiceText.formatDetailLine(
                        status = snapshot.primaryIssue,
                        lastCaptureAt = snapshot.lastCaptureAt
                    )
                    "$detail\n${ServiceText.formatKeepAliveLine(snapshot.foregroundServiceEnabled, snapshot.ignoringBatteryOptimizations)}"
                }
            )
        )
        .setContentIntent(createContentIntent())
        .addAction(
            0,
            getString(R.string.keepalive_stop_action),
            createStopPendingIntent()
        )
        .build()

    private fun createContentIntent(): PendingIntent {
        val intent = Intent(this, MainActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
        return PendingIntent.getActivity(
            this,
            0,
            intent,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
    }

    private fun createStopPendingIntent(): PendingIntent {
        val intent = Intent(this, CompanionForegroundService::class.java).setAction(ACTION_STOP)
        return PendingIntent.getService(
            this,
            1,
            intent,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return

        val channel = NotificationChannel(
            CHANNEL_ID,
            getString(R.string.keepalive_notification_channel_name),
            NotificationManager.IMPORTANCE_LOW
        ).apply {
            description = getString(R.string.keepalive_notification_channel_description)
            setShowBadge(false)
        }

        getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
    }

    companion object {
        private const val CHANNEL_ID = "companion_keepalive"
        private const val NOTIFICATION_ID = 0xCA11
        private const val REFRESH_INTERVAL_MS = 15_000L
        private const val ACTION_STOP = "com.gamehelper.androidcontrol.action.STOP_KEEPALIVE"

        fun start(context: Context) {
            val intent = Intent(context, CompanionForegroundService::class.java)
            ContextCompat.startForegroundService(context, intent)
        }

        fun stop(context: Context) {
            context.stopService(Intent(context, CompanionForegroundService::class.java))
        }
    }
}

private object ServiceText {
    fun formatStatusLine(status: String, activePackageName: String?): String {
        return when {
            status == "助手就绪。" && !activePackageName.isNullOrBlank() -> {
                "已连接：$activePackageName"
            }

            status == "保活配置未完成。" -> "保活配置未完成"
            else -> status
        }
    }

    fun formatDetailLine(status: String, lastCaptureAt: String?): String {
        val captureText = lastCaptureAt ?: "暂无快照"
        return "$status  最近抓取：$captureText"
    }

    fun formatKeepAliveLine(foregroundEnabled: Boolean, ignoringBatteryOptimizations: Boolean): String {
        val notificationState = if (foregroundEnabled) "已开启" else "已关闭"
        val batteryState = if (ignoringBatteryOptimizations) "已豁免" else "未豁免"
        return "常驻通知：$notificationState，电池优化：$batteryState"
    }
}
