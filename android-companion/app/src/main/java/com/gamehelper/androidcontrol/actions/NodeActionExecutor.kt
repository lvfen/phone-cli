package com.gamehelper.androidcontrol.actions

import android.os.Bundle
import android.view.accessibility.AccessibilityNodeInfo
import com.gamehelper.androidcontrol.capture.HierarchyCaptureManager
import com.gamehelper.androidcontrol.model.FallbackBoundsDto
import com.gamehelper.androidcontrol.model.FindNodeResultItemDto
import com.gamehelper.androidcontrol.model.NodeActionRequestDto

class NodeActionExecutor(
    private val captureManager: HierarchyCaptureManager,
    private val gestureExecutor: GestureExecutor
) {

    fun clickNode(request: NodeActionRequestDto): Boolean {
        val liveNode = captureManager.findLiveNodeById(request.nodeId)
        val clicked = clickLiveNode(liveNode)
        if (clicked) return true

        val fallback = request.fallbackBounds ?: return false
        return gestureExecutor.tap(fallback.centerX, fallback.centerY)
    }

    fun setText(nodeId: String, text: String): Boolean {
        val liveNode = captureManager.findLiveNodeById(nodeId) ?: return false
        val args = Bundle().apply {
            putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, text)
        }
        return liveNode.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args)
    }

    fun clickResolved(item: FindNodeResultItemDto): Boolean {
        val resolved = item.resolvedClick
        val targetNodeId = resolved.nodeId ?: item.nodeId
        val liveNode = captureManager.findLiveNodeById(targetNodeId)
        val clicked = clickLiveNode(liveNode)
        if (clicked) return true
        return gestureExecutor.tap(resolved.center.x, resolved.center.y)
    }

    fun setTextOnFocused(text: String): Boolean {
        val liveNode = captureManager.findFocusedNode() ?: return false
        val args = Bundle().apply {
            putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, text)
        }
        return liveNode.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args)
    }

    fun fallbackTap(bounds: FallbackBoundsDto): Boolean {
        return gestureExecutor.tap(bounds.centerX, bounds.centerY)
    }

    private fun clickLiveNode(node: AccessibilityNodeInfo?): Boolean {
        var current = node
        while (current != null) {
            if (current.isClickable && current.performAction(AccessibilityNodeInfo.ACTION_CLICK)) {
                return true
            }
            current = current.parent
        }
        return false
    }
}
