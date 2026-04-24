package com.gamehelper.androidcontrol.actions

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.graphics.Path
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

class GestureExecutor(
    private val service: AccessibilityService
) {

    fun tap(x: Int, y: Int): Boolean {
        val path = Path().apply { moveTo(x.toFloat(), y.toFloat()) }
        return dispatch(path, TAP_DURATION_MS)
    }

    fun doubleTap(x: Int, y: Int, intervalMs: Long = 100): Boolean {
        val first = tap(x, y)
        if (!first) return false
        Thread.sleep(intervalMs)
        return tap(x, y)
    }

    fun longPress(x: Int, y: Int, durationMs: Long = 3000): Boolean {
        val path = Path().apply { moveTo(x.toFloat(), y.toFloat()) }
        return dispatch(path, durationMs)
    }

    fun pressBack(): Boolean {
        return service.performGlobalAction(AccessibilityService.GLOBAL_ACTION_BACK)
    }

    fun pressHome(): Boolean {
        return service.performGlobalAction(AccessibilityService.GLOBAL_ACTION_HOME)
    }

    fun swipe(startX: Int, startY: Int, endX: Int, endY: Int, durationMs: Long): Boolean {
        val path = Path().apply {
            moveTo(startX.toFloat(), startY.toFloat())
            lineTo(endX.toFloat(), endY.toFloat())
        }
        return dispatch(path, durationMs)
    }

    private fun dispatch(path: Path, durationMs: Long): Boolean {
        val latch = CountDownLatch(1)
        val success = AtomicBoolean(false)
        val gesture = GestureDescription.Builder()
            .addStroke(GestureDescription.StrokeDescription(path, 0L, durationMs))
            .build()

        service.dispatchGesture(
            gesture,
            object : AccessibilityService.GestureResultCallback() {
                override fun onCompleted(gestureDescription: GestureDescription?) {
                    success.set(true)
                    latch.countDown()
                }

                override fun onCancelled(gestureDescription: GestureDescription?) {
                    success.set(false)
                    latch.countDown()
                }
            },
            null
        )

        // On busy devices (e.g. Huawei EMUI running games/Flutter), the
        // accessibility framework can delay the result callback well beyond
        // the gesture's nominal duration. Give the callback a generous 5s
        // budget on top of the gesture duration so short taps don't get
        // reported as failures and force-fallback to ADB.
        latch.await(durationMs + CALLBACK_BUDGET_MS, TimeUnit.MILLISECONDS)
        return success.get()
    }

    companion object {
        private const val TAP_DURATION_MS: Long = 60L
        private const val CALLBACK_BUDGET_MS: Long = 5000L
    }
}
