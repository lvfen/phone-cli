package com.gamehelper.androidcontrol

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.widget.Button
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.graphics.Insets
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.updatePadding
import com.gamehelper.androidcontrol.foreground.CompanionForegroundService
import com.gamehelper.androidcontrol.keepalive.BatteryOptimizationHelper
import com.gamehelper.androidcontrol.keepalive.CompanionDiagnosticReader
import com.gamehelper.androidcontrol.keepalive.DiagnosticSnapshot
import com.gamehelper.androidcontrol.keepalive.OverlayPermissionHelper

class MainActivity : AppCompatActivity() {

    private val handler = Handler(Looper.getMainLooper())
    private val diagnosticReader by lazy { CompanionDiagnosticReader(this) }
    private val batteryOptimizationHelper by lazy { BatteryOptimizationHelper(this) }
    private val overlayPermissionHelper by lazy { OverlayPermissionHelper(this) }

    private lateinit var summaryView: TextView
    private lateinit var accessibilityStatusView: TextView
    private lateinit var serviceStatusView: TextView
    private lateinit var notificationStatusView: TextView
    private lateinit var overlayStatusView: TextView
    private lateinit var batteryStatusView: TextView
    private lateinit var portStatusView: TextView
    private lateinit var captureStatusView: TextView
    private lateinit var detailStatusView: TextView
    private lateinit var foregroundToggleButton: Button
    private lateinit var overlayToggleButton: Button

    private var startKeepAliveAfterPermission = false
    private var startOverlayAfterNotificationPermission = false
    private var startOverlayAfterOverlayPermission = false

    private val refreshRunnable = object : Runnable {
        override fun run() {
            refreshDiagnosticViews()
            handler.postDelayed(this, 3_000L)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val density = resources.displayMetrics.density
        val padding = (20 * density).toInt()
        val sectionSpacing = (16 * density).toInt()
        val cardRadius = 24f * density
        val contentPadding = (18 * density).toInt()
        val insetSpacing = (12 * density).toInt()

        val root = FrameLayout(this).apply {
            setBackgroundColor(color(R.color.surface))
        }

        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(padding, padding, padding, padding)
        }

        val heroCard = cardContainer(cardRadius, intArrayOf(color(R.color.hero_start), color(R.color.hero_end)))
        val heroContent = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(padding, padding, padding, padding)
        }
        val title = titleText(getString(R.string.app_name), 28f)
        val heroHeadline = bodyText(getString(R.string.hero_title), 18f, true)
        val heroSubtitle = subtleText(getString(R.string.hero_subtitle)).apply {
            setPadding(0, (8 * density).toInt(), 0, 0)
        }
        val heroBadge = badgeText(getString(R.string.hero_badge)).apply {
            setPadding((12 * density).toInt(), (6 * density).toInt(), (12 * density).toInt(), (6 * density).toInt())
        }
        heroContent.addView(heroBadge)
        heroContent.addView(title)
        heroContent.addView(heroHeadline)
        heroContent.addView(heroSubtitle)
        heroCard.addView(heroContent)

        val statusSection = sectionCard(getString(R.string.section_status_title), cardRadius, contentPadding)
        val statusCard = statusSection.content
        summaryView = metricTitleText()
        accessibilityStatusView = metricText()
        serviceStatusView = metricText()
        notificationStatusView = metricText()
        overlayStatusView = metricText()
        batteryStatusView = metricText()
        portStatusView = metricText()
        captureStatusView = detailText()
        listOf(
            summaryView,
            accessibilityStatusView,
            serviceStatusView,
            notificationStatusView,
            overlayStatusView,
            batteryStatusView,
            portStatusView,
            captureStatusView,
        ).forEach { statusCard.addView(it) }

        val actionSection = sectionCard(getString(R.string.section_actions_title), cardRadius, contentPadding)
        val actionCard = actionSection.content

        val accessibilityButton = button(getString(R.string.action_open_accessibility_settings)) {
            startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
        }
        val refreshButton = button(getString(R.string.action_refresh_status)) {
            refreshDiagnosticViews()
        }
        foregroundToggleButton = button(getString(R.string.action_start_keepalive)) {
            toggleForegroundService()
        }
        overlayToggleButton = button(getString(R.string.action_enable_overlay)) {
            toggleOverlayKeepAlive()
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
            accessibilityButton,
            refreshButton,
            foregroundToggleButton,
            overlayToggleButton,
            batteryRequestButton,
            batterySettingsButton,
            romGuideButton
        ).forEach { view ->
            actionCard.addView(view)
        }

        val detailSection = sectionCard(getString(R.string.section_details_title), cardRadius, contentPadding)
        val detailCard = detailSection.content
        val instructions = subtleText(getString(R.string.main_instructions)).apply {
            setPadding(0, 0, 0, (12 * density).toInt())
        }
        detailStatusView = detailText()
        detailCard.addView(instructions)
        detailCard.addView(detailStatusView)

        listOf(heroCard, statusSection.card, actionSection.card, detailSection.card).forEachIndexed { index, view ->
            if (index > 0) {
                (view.layoutParams as? LinearLayout.LayoutParams)?.topMargin = sectionSpacing
            }
            container.addView(view)
        }

        val scrollView = ScrollView(this).apply {
            addView(container)
        }

        ViewCompat.setOnApplyWindowInsetsListener(root) { _, insets ->
            val systemBars = insets.getInsets(WindowInsetsCompat.Type.systemBars())
            val imeInsets = insets.getInsets(WindowInsetsCompat.Type.ime())
            val bottomInset = maxOf(systemBars.bottom, imeInsets.bottom)
            val topInset = systemBars.top
            val horizontalInset = Insets.max(systemBars, imeInsets)

            scrollView.updatePadding(
                left = horizontalInset.left,
                top = topInset,
                right = horizontalInset.right,
                bottom = bottomInset,
            )

            container.updatePadding(
                left = padding + insetSpacing,
                top = padding + insetSpacing,
                right = padding + insetSpacing,
                bottom = padding + insetSpacing,
            )

            WindowInsetsCompat.CONSUMED
        }

        root.addView(scrollView)
        setContentView(root)
        ViewCompat.requestApplyInsets(root)
        refreshDiagnosticViews()
    }

    override fun onResume() {
        super.onResume()
        if (startOverlayAfterOverlayPermission && overlayPermissionHelper.canDrawOverlays()) {
            startOverlayAfterOverlayPermission = false
            enableOverlayKeepAlive()
        }
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
            }
            if (granted && startOverlayAfterNotificationPermission) {
                enableOverlayKeepAlive()
            }
            if (!granted) {
                toast(getString(R.string.message_notification_permission_denied))
            }
            startKeepAliveAfterPermission = false
            startOverlayAfterNotificationPermission = false
            refreshDiagnosticViews()
        }
    }

    private fun refreshDiagnosticViews() {
        val snapshot = diagnosticReader.snapshot()

        summaryView.text = getString(R.string.status_summary, snapshot.primaryIssue)
        summaryView.setTextColor(statusColor(snapshot))
        accessibilityStatusView.text = buildAccessibilityLine(snapshot)
        serviceStatusView.text = getString(R.string.status_service_connected, yesNo(snapshot.serviceConnected))
        notificationStatusView.text =
            getString(R.string.status_keepalive, yesNo(snapshot.foregroundServiceEnabled))
        overlayStatusView.text = getString(
            R.string.status_overlay,
            yesNo(snapshot.overlayEnabled),
            yesNo(snapshot.overlayPermissionGranted),
            yesNo(snapshot.overlayVisible),
        )
        batteryStatusView.text =
            getString(R.string.status_battery, yesNo(snapshot.ignoringBatteryOptimizations))
        portStatusView.text =
            getString(R.string.status_ports, yesNo(snapshot.httpPortReachable), yesNo(snapshot.webSocketPortReachable))
        captureStatusView.text =
            buildString {
                append(
                    getString(
                        R.string.status_capture,
                        snapshot.lastCaptureAt ?: getString(R.string.none),
                        snapshot.activePackageName ?: getString(R.string.unknown),
                    )
                )
            }
        detailStatusView.text = if (snapshot.details.isNotEmpty()) {
            getString(R.string.status_detail_prefix, snapshot.details.joinToString("\n"))
        } else {
            getString(R.string.status_detail_empty)
        }

        foregroundToggleButton.text = if (snapshot.foregroundServiceEnabled) {
            getString(R.string.action_stop_keepalive)
        } else {
            getString(R.string.action_start_keepalive)
        }

        overlayToggleButton.text = if (snapshot.overlayEnabled) {
            getString(R.string.action_disable_overlay)
        } else {
            getString(R.string.action_enable_overlay)
        }
    }

    private fun buildAccessibilityLine(snapshot: DiagnosticSnapshot): String {
        return getString(
            R.string.status_accessibility,
            yesNo(snapshot.accessibilityEnabled),
            yesNo(snapshot.serviceEnabled),
        )
    }

    private fun toggleForegroundService() {
        if (diagnosticReader.isForegroundKeepAliveEnabled()) {
            if (diagnosticReader.isOverlayEnabled()) {
                toast(getString(R.string.message_overlay_requires_notification))
                return
            }
            diagnosticReader.setForegroundKeepAliveEnabled(false)
            syncKeepAliveHostService()
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
        syncKeepAliveHostService()
        refreshDiagnosticViews()
    }

    private fun toggleOverlayKeepAlive() {
        if (diagnosticReader.isOverlayEnabled()) {
            diagnosticReader.setOverlayEnabled(false)
            syncKeepAliveHostService()
            refreshDiagnosticViews()
            return
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) {
            startOverlayAfterNotificationPermission = true
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), REQUEST_POST_NOTIFICATIONS)
            return
        }

        if (!overlayPermissionHelper.canDrawOverlays()) {
            startOverlayAfterOverlayPermission = true
            openOverlayPermissionSettings()
            return
        }

        enableOverlayKeepAlive()
        refreshDiagnosticViews()
    }

    private fun enableOverlayKeepAlive() {
        if (!overlayPermissionHelper.canDrawOverlays()) {
            toast(getString(R.string.message_overlay_permission_denied))
            return
        }

        diagnosticReader.setForegroundKeepAliveEnabled(true)
        diagnosticReader.setOverlayEnabled(true)
        syncKeepAliveHostService()
    }

    private fun syncKeepAliveHostService() {
        if (diagnosticReader.isForegroundKeepAliveEnabled() || diagnosticReader.isOverlayEnabled()) {
            CompanionForegroundService.start(this)
        } else {
            CompanionForegroundService.stop(this)
        }
    }

    private fun openOverlayPermissionSettings() {
        runCatching {
            startActivity(overlayPermissionHelper.createManageOverlayPermissionIntent())
        }.onFailure {
            startOverlayAfterOverlayPermission = false
            toast(getString(R.string.message_cannot_open_overlay_settings))
        }
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
            isAllCaps = false
            setTextColor(color(R.color.on_primary))
            background = GradientDrawable().apply {
                cornerRadius = 18f * resources.displayMetrics.density
                setColor(color(R.color.primary))
            }
            setPadding(0, (14 * resources.displayMetrics.density).toInt(), 0, (14 * resources.displayMetrics.density).toInt())
            val lp = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            )
            lp.topMargin = (10 * resources.displayMetrics.density).toInt()
            layoutParams = lp
            setOnClickListener { onClick() }
        }
    }

    private fun toast(message: String) {
        Toast.makeText(this, message, Toast.LENGTH_SHORT).show()
    }

    private fun titleText(text: String, size: Float): TextView = TextView(this).apply {
        this.text = text
        textSize = size
        setTextColor(color(R.color.text_primary))
        setTypeface(typeface, Typeface.BOLD)
    }

    private fun bodyText(text: String, size: Float = 16f, bold: Boolean = false): TextView = TextView(this).apply {
        this.text = text
        textSize = size
        setTextColor(color(R.color.text_primary))
        if (bold) setTypeface(typeface, Typeface.BOLD)
    }

    private fun subtleText(text: String): TextView = TextView(this).apply {
        this.text = text
        textSize = 14f
        setTextColor(color(R.color.text_secondary))
    }

    private fun badgeText(text: String): TextView = TextView(this).apply {
        this.text = text
        textSize = 12f
        setTextColor(color(R.color.primary_dark))
        setTypeface(typeface, Typeface.BOLD)
        background = GradientDrawable().apply {
            cornerRadius = 999f
            setColor(color(R.color.surface_alt))
        }
        layoutParams = LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.WRAP_CONTENT,
            LinearLayout.LayoutParams.WRAP_CONTENT
        ).apply {
            bottomMargin = (14 * resources.displayMetrics.density).toInt()
        }
    }

    private fun metricTitleText(): TextView = bodyText("", 17f, true).apply {
        setPadding(0, (8 * resources.displayMetrics.density).toInt(), 0, 0)
    }

    private fun metricText(): TextView = bodyText("", 15f).apply {
        setPadding(0, (8 * resources.displayMetrics.density).toInt(), 0, 0)
    }

    private fun detailText(): TextView = subtleText("").apply {
        setPadding(0, (12 * resources.displayMetrics.density).toInt(), 0, 0)
        setLineSpacing(0f, 1.15f)
    }

    private fun sectionCard(title: String, radius: Float, padding: Int): SectionCard {
        val card = cardContainer(radius, intArrayOf(color(R.color.surface_card), color(R.color.surface_card)))
        val content = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(padding, padding, padding, padding)
            addView(bodyText(title, 18f, true))
        }
        card.addView(content)
        return SectionCard(card, content)
    }

    private fun cardContainer(radius: Float, colors: IntArray): FrameLayout = FrameLayout(this).apply {
        background = GradientDrawable(GradientDrawable.Orientation.TL_BR, colors).apply {
            cornerRadius = radius
            setStroke((1.2f * resources.displayMetrics.density).toInt(), color(R.color.border_soft))
        }
        layoutParams = LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT
        )
    }

    private fun statusColor(snapshot: DiagnosticSnapshot): Int = when (snapshot.issueCode) {
        "READY" -> color(R.color.status_green)
        "KEEPALIVE_INCOMPLETE", "OVERLAY_INCOMPLETE" -> color(R.color.status_amber)
        else -> color(R.color.status_red)
    }

    private fun color(id: Int): Int = ContextCompat.getColor(this, id)

    private fun yesNo(value: Boolean): String = if (value) getString(R.string.yes) else getString(R.string.no)

    private data class SectionCard(
        val card: FrameLayout,
        val content: LinearLayout
    )

    companion object {
        private const val REQUEST_POST_NOTIFICATIONS = 1001
    }
}
