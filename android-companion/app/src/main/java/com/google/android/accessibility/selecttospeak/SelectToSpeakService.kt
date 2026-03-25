package com.google.android.accessibility.selecttospeak

import android.accessibilityservice.AccessibilityServiceInfo
import android.util.Log
import com.gamehelper.androidcontrol.accessibility.ControlAccessibilityService

class SelectToSpeakService : ControlAccessibilityService() {

    override fun onServiceConnected() {
        Log.d(TAG, "onServiceConnected")
        val info = serviceInfo
        info.flags = info.flags or
            AccessibilityServiceInfo.FLAG_INCLUDE_NOT_IMPORTANT_VIEWS or
            AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS or
            AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS or
            AccessibilityServiceInfo.FLAG_REQUEST_FILTER_KEY_EVENTS
        setServiceInfo(info)
        super.onServiceConnected()
    }

    companion object {
        private val TAG = SelectToSpeakService::class.java.simpleName
    }
}
