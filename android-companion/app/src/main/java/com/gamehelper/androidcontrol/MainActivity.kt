package com.gamehelper.androidcontrol

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.gamehelper.androidcontrol.foreground.CompanionForegroundService
import com.gamehelper.androidcontrol.keepalive.BatteryOptimizationHelper
import com.gamehelper.androidcontrol.keepalive.CompanionDiagnosticReader
import com.gamehelper.androidcontrol.keepalive.DiagnosticSnapshot

class MainActivity : AppCompatActivity() {

    private val handler = Handler(Looper.getMainLooper())
    private val diagnosticReader by lazy { CompanionDiagnosticReader(this) }
    private val batteryOptimizationHelper by lazy { BatteryOptimizationHelper(this) }

    private lateinit var summaryView: TextView
    private lateinit var accessibilityStatusView: TextView
    private lateinit var serviceStatusView: TextView
    private lateinit var notificationStatusView: TextView
    private lateinit var batteryStatusView: TextView
    private lateinit var portStatusView: TextView
    private lateinit var captureStatusView: TextView
    private lateinit var foregroundToggleButton: Button

    private var startKeepAliveAfterPermission = false

    private val refreshRunnable = object : Runnable {
        override fun run() {
            refreshDiagnosticViews()
            handler.postDelayed(this, 3_000L)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val padding = (20 * resources.displayMetrics.density).toInt()
        val sectionSpacing = (12 * resources.displayMetrics.density).toInt()

        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(padding, padding, padding, padding)
        }

        val title = TextView(this).apply {
            text = getString(R.string.app_name)
            textSize = 22f
        }

        val instructions = TextView(this).apply {
            text = getString(R.string.main_instructions)
            textSize = 15f
            setPadding(0, sectionSpacing, 0, sectionSpacing)
        }

        summaryView = TextView(this)
        accessibilityStatusView = TextView(this)
        serviceStatusView = TextView(this)
        notificationStatusView = TextView(this)
        batteryStatusView = TextView(this)
        portStatusView = TextView(this)
        captureStatusView = TextView(this)

        val accessibilityButton = button(getString(R.string.action_open_accessibility_settings)) {
            startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
        }
        val refreshButton = button(getString(R.string.action_refresh_status)) {
            refreshDiagnosticViews()
        }
        foregroundToggleButton = button(getString(R.string.action_start_keepalive)) {
            toggleForegroundService()
        }
        val batteryRequestButton = button(getString(R.string.action_request_battery_optimization_whitelist)) {
            if (!batteryOptimizationHelper.requestIgnoreBatteryOptimizations()) {
                toast(getString(R.string.message_cannot_open_battery_optimization_request))
            }
        }
        val batterySettingsButton = button(getString(R.string.action_open_battery_optimization_settings)) {
            if (!batteryOptimizationHelper.openBatteryOptimizationSettings()) {
                toast(getString(R.string.message_cannot_open_battery_optimization_settings))
            }
        }
        val romGuideButton = button(getString(R.string.action_open_rom_keepalive_guide)) {
            showRomGuide()
        }

        listOf(
            title,
            instructions,
            summaryView,
            accessibilityStatusView,
            serviceStatusView,
            notificationStatusView,
            batteryStatusView,
            portStatusView,
            captureStatusView,
            accessibilityButton,
            refreshButton,
            foregroundToggleButton,
            batteryRequestButton,
            batterySettingsButton,
            romGuideButton
        ).forEach { view ->
            if (view !== title) {
                (view.layoutParams as? LinearLayout.LayoutParams)?.topMargin = sectionSpacing
            }
            container.addView(view)
        }

        val scrollView = ScrollView(this).apply {
            addView(container)
        }

        setContentView(scrollView)
        refreshDiagnosticViews()
    }

    override fun onResume() {
        super.onResume()
        handler.post(refreshRunnable)
    }

    override fun onPause() {
        handler.removeCallbacks(refreshRunnable)
        super.onPause()
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == REQUEST_POST_NOTIFICATIONS) {
            val granted = grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED
            if (granted && startKeepAliveAfterPermission) {
                enableForegroundService()
            } else if (!granted) {
                toast(getString(R.string.message_notification_permission_denied))
            }
            startKeepAliveAfterPermission = false
            refreshDiagnosticViews()
        }
    }

    private fun refreshDiagnosticViews() {
        val snapshot = diagnosticReader.snapshot()

        summaryView.text = "Summary: ${snapshot.primaryIssue}"
        accessibilityStatusView.text = buildAccessibilityLine(snapshot)
        serviceStatusView.text = "Accessibility service connected: ${yesNo(snapshot.serviceConnected)}"
        notificationStatusView.text =
            "Keep-alive notification enabled: ${yesNo(snapshot.foregroundServiceEnabled)}"
        batteryStatusView.text =
            "Ignoring battery optimizations: ${yesNo(snapshot.ignoringBatteryOptimizations)}"
        portStatusView.text =
            "Loopback ports: 17342=${yesNo(snapshot.httpPortReachable)}, 17343=${yesNo(snapshot.webSocketPortReachable)}"
        captureStatusView.text =
            "Last capture: ${snapshot.lastCaptureAt ?: "none"} | Package: ${snapshot.activePackageName ?: "unknown"}"

        foregroundToggleButton.text = if (snapshot.foregroundServiceEnabled) {
            getString(R.string.action_stop_keepalive)
        } else {
            getString(R.string.action_start_keepalive)
        }
    }

    private fun buildAccessibilityLine(snapshot: DiagnosticSnapshot): String {
        return "Accessibility: global=${yesNo(snapshot.accessibilityEnabled)}, service=${yesNo(snapshot.serviceEnabled)}"
    }

    private fun toggleForegroundService() {
        if (diagnosticReader.isForegroundKeepAliveEnabled()) {
            diagnosticReader.setForegroundKeepAliveEnabled(false)
            CompanionForegroundService.stop(this)
            refreshDiagnosticViews()
            return
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) {
            startKeepAliveAfterPermission = true
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), REQUEST_POST_NOTIFICATIONS)
            return
        }

        enableForegroundService()
    }

    private fun enableForegroundService() {
        diagnosticReader.setForegroundKeepAliveEnabled(true)
        CompanionForegroundService.start(this)
        refreshDiagnosticViews()
    }

    private fun showRomGuide() {
        AlertDialog.Builder(this)
            .setTitle(R.string.rom_keepalive_dialog_title)
            .setMessage(getString(R.string.rom_keepalive_dialog_message))
            .setPositiveButton(android.R.string.ok, null)
            .show()
    }

    private fun button(text: String, onClick: () -> Unit): Button {
        return Button(this).apply {
            this.text = text
            setOnClickListener { onClick() }
        }
    }

    private fun toast(message: String) {
        Toast.makeText(this, message, Toast.LENGTH_SHORT).show()
    }

    private fun yesNo(value: Boolean): String = if (value) "yes" else "no"

    companion object {
        private const val REQUEST_POST_NOTIFICATIONS = 1001
    }
}
