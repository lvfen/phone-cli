package com.gamehelper.androidcontrol.overlay

import android.content.Context
import android.content.Intent
import android.graphics.PixelFormat
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Build
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.WindowInsets
import android.view.WindowManager
import android.widget.TextView
import androidx.core.content.ContextCompat
import com.gamehelper.androidcontrol.MainActivity
import com.gamehelper.androidcontrol.R
import com.gamehelper.androidcontrol.keepalive.CompanionDiagnosticReader
import com.gamehelper.androidcontrol.keepalive.CompanionRuntimeState
import com.gamehelper.androidcontrol.keepalive.DiagnosticSnapshot
import com.gamehelper.androidcontrol.keepalive.OverlayPermissionHelper
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min

class CompanionOverlayController(
    context: Context,
    private val diagnosticReader: CompanionDiagnosticReader,
    private val overlayPermissionHelper: OverlayPermissionHelper = OverlayPermissionHelper(context)
) {

    private val appContext = context.applicationContext
    private val windowManager = appContext.getSystemService(WindowManager::class.java)
    private val density = appContext.resources.displayMetrics.density
    private val widthPx = max((10 * density).toInt(), 10)
    private val heightPx = (42 * density).toInt()
    private val safeTopExtraPx = (18 * density).toInt()
    private val safeBottomExtraPx = (72 * density).toInt()
    private val dragSlopPx = 8 * density
    private val longPressTimeoutMs = 500L

    private var overlayView: TextView? = null

    fun sync(snapshot: DiagnosticSnapshot = diagnosticReader.snapshot()) {
        CompanionRuntimeState.overlayPermissionGranted = overlayPermissionHelper.canDrawOverlays()

        if (!snapshot.overlayEnabled || !overlayPermissionHelper.canDrawOverlays()) {
            hide()
            return
        }

        if (overlayView == null) {
            show(snapshot)
        } else {
            render(snapshot)
        }
    }

    fun hide() {
        overlayView?.let { view ->
            runCatching { windowManager.removeView(view) }
        }
        overlayView = null
        CompanionRuntimeState.overlayVisible = false
    }

    private fun show(snapshot: DiagnosticSnapshot) {
        val params = buildLayoutParams()
        val position = diagnosticReader.loadOverlayPosition() ?: defaultPosition()
        val clamped = clampPosition(position.first, position.second)
        params.x = clamped.first
        params.y = clamped.second

        val view = createOverlayView(params)
        render(snapshot, view)

        runCatching {
            windowManager.addView(view, params)
            overlayView = view
            CompanionRuntimeState.overlayVisible = true
        }.onFailure {
            overlayView = null
            CompanionRuntimeState.overlayVisible = false
        }
    }

    private fun render(snapshot: DiagnosticSnapshot, targetView: TextView? = overlayView) {
        val view = targetView ?: return
        view.text = when (snapshot.issueCode) {
            "READY" -> appContext.getString(R.string.overlay_label_ready)
            "KEEPALIVE_INCOMPLETE", "OVERLAY_INCOMPLETE" -> appContext.getString(R.string.overlay_label_warning)
            else -> appContext.getString(R.string.overlay_label_error)
        }
        view.background = GradientDrawable().apply {
            shape = GradientDrawable.RECTANGLE
            cornerRadius = 5f * density
            setColor(
                when (snapshot.issueCode) {
                    "READY" -> color(R.color.status_green)
                    "KEEPALIVE_INCOMPLETE", "OVERLAY_INCOMPLETE" -> color(R.color.status_amber)
                    else -> color(R.color.status_red)
                }
            )
            alpha = 230
        }
        view.contentDescription = snapshot.primaryIssue
        CompanionRuntimeState.overlayVisible = true
    }

    private fun createOverlayView(params: WindowManager.LayoutParams): TextView {
        return TextView(appContext).apply {
            textSize = 7f
            typeface = Typeface.DEFAULT_BOLD
            gravity = Gravity.CENTER
            setTextColor(color(R.color.on_primary))
            setPadding(0, 0, 0, 0)
            setOnTouchListener(OverlayTouchListener(params, this))
        }
    }

    private fun buildLayoutParams(): WindowManager.LayoutParams {
        return WindowManager.LayoutParams(
            widthPx,
            heightPx,
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
            } else {
                @Suppress("DEPRECATION")
                WindowManager.LayoutParams.TYPE_PHONE
            },
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
            PixelFormat.TRANSLUCENT
        ).apply {
            gravity = Gravity.TOP or Gravity.START
        }
    }

    private fun defaultPosition(): Pair<Int, Int> {
        val metrics = appContext.resources.displayMetrics
        val width = metrics.widthPixels
        val height = metrics.heightPixels
        val top = safeTopInset()
        val bottom = safeBottomInset()
        val x = width - widthPx
        val y = max(top, ((height - top - bottom - heightPx) * 0.38f).toInt() + top)
        return clampPosition(x, y)
    }

    private fun clampPosition(x: Int, y: Int): Pair<Int, Int> {
        val metrics = appContext.resources.displayMetrics
        val width = metrics.widthPixels
        val height = metrics.heightPixels
        val topBound = safeTopInset()
        val bottomBound = max(topBound, height - heightPx - safeBottomInset())
        val rightBound = max(0, width - widthPx)
        return min(max(0, x), rightBound) to min(max(topBound, y), bottomBound)
    }

    private fun safeTopInset(): Int {
        val base = safeTopExtraPx
        val inset = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            windowManager.currentWindowMetrics.windowInsets
                .getInsetsIgnoringVisibility(WindowInsets.Type.statusBars()).top
        } else {
            0
        }
        return base + inset
    }

    private fun safeBottomInset(): Int {
        val base = safeBottomExtraPx
        val inset = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            windowManager.currentWindowMetrics.windowInsets
                .getInsetsIgnoringVisibility(WindowInsets.Type.navigationBars()).bottom
        } else {
            0
        }
        return base + inset
    }

    private fun color(id: Int): Int = ContextCompat.getColor(appContext, id)

    private fun openMainActivity() {
        val intent = Intent(appContext, MainActivity::class.java).apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
        }
        appContext.startActivity(intent)
    }

    private inner class OverlayTouchListener(
        private val params: WindowManager.LayoutParams,
        private val view: View
    ) : View.OnTouchListener {

        private val longPressRunnable = Runnable {
            openMainActivity()
        }

        private var downRawX = 0f
        private var downRawY = 0f
        private var startX = 0
        private var startY = 0
        private var dragging = false
        private var longPressTriggered = false

        override fun onTouch(target: View, event: MotionEvent): Boolean {
            when (event.actionMasked) {
                MotionEvent.ACTION_DOWN -> {
                    downRawX = event.rawX
                    downRawY = event.rawY
                    startX = params.x
                    startY = params.y
                    dragging = false
                    longPressTriggered = false
                    target.postDelayed(longPressRunnable, longPressTimeoutMs)
                    return true
                }

                MotionEvent.ACTION_MOVE -> {
                    val deltaX = (event.rawX - downRawX).toInt()
                    val deltaY = (event.rawY - downRawY).toInt()
                    if (!dragging && (abs(deltaX) > dragSlopPx || abs(deltaY) > dragSlopPx)) {
                        dragging = true
                        target.removeCallbacks(longPressRunnable)
                    }
                    if (dragging) {
                        val clamped = clampPosition(startX + deltaX, startY + deltaY)
                        params.x = clamped.first
                        params.y = clamped.second
                        runCatching { windowManager.updateViewLayout(view, params) }
                    }
                    return true
                }

                MotionEvent.ACTION_UP,
                MotionEvent.ACTION_CANCEL -> {
                    target.removeCallbacks(longPressRunnable)
                    if (dragging) {
                        val snapped = snapToEdge(params.x, params.y)
                        params.x = snapped.first
                        params.y = snapped.second
                        diagnosticReader.saveOverlayPosition(params.x, params.y)
                        runCatching { windowManager.updateViewLayout(view, params) }
                    }
                    return true
                }
            }
            return false
        }
    }

    private fun snapToEdge(x: Int, y: Int): Pair<Int, Int> {
        val metrics = appContext.resources.displayMetrics
        val leftDistance = abs(x)
        val rightEdge = max(0, metrics.widthPixels - widthPx)
        val rightDistance = abs(rightEdge - x)
        val snappedX = if (leftDistance <= rightDistance) 0 else rightEdge
        return clampPosition(snappedX, y)
    }
}
