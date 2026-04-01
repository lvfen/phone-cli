package com.gamehelper.androidcontrol.capture

import android.accessibilityservice.AccessibilityService
import android.graphics.Rect
import android.view.accessibility.AccessibilityNodeInfo
import android.view.accessibility.AccessibilityWindowInfo
import com.gamehelper.androidcontrol.model.BoundsDto
import com.gamehelper.androidcontrol.model.CenterDto
import com.gamehelper.androidcontrol.model.UiNodeDto
import com.gamehelper.androidcontrol.model.UiSnapshotDto
import com.gamehelper.androidcontrol.model.WindowDto
import com.gamehelper.androidcontrol.store.SnapshotStore
import java.time.Instant

class HierarchyCaptureManager(
    private val service: AccessibilityService,
    private val snapshotStore: SnapshotStore
) {
    @Volatile
    private var lastCaptureTimeMs = 0L

    @Synchronized
    fun captureLatest(): UiSnapshotDto? {
        val candidateWindows = service.windows.orEmpty()
            .filterNot(::isCompanionWindow)
        val root = selectCaptureRoot(candidateWindows) ?: return null
        val windows = candidateWindows.map(::captureWindow)
        val activeWindow = windows.firstOrNull { it.isActive }
        val raw = UiSnapshotDto(
            capturedAt = Instant.now().toString(),
            packageName = activeWindow?.packageName ?: root.packageName?.toString(),
            windows = windows,
            root = captureNode(root, "0", windowId = activeWindow?.windowId)
        )
        val pruned = raw.copy(root = raw.root?.let(Companion::pruneNodeForSnapshot))
        snapshotStore.update(pruned)
        lastCaptureTimeMs = System.currentTimeMillis()
        return pruned
    }

    fun captureWithCache(maxAgeMs: Long = 500): UiSnapshotDto? {
        val stored = snapshotStore.getSnapshot()
        if (stored != null) {
            val age = System.currentTimeMillis() - lastCaptureTimeMs
            if (age < maxAgeMs) return stored
        }
        return captureLatest()
    }

    fun latestSnapshot(): UiSnapshotDto? = snapshotStore.getSnapshot()

    fun findLiveNodeById(nodeId: String): AccessibilityNodeInfo? {
        val root = selectCaptureRoot(service.windows.orEmpty().filterNot(::isCompanionWindow)) ?: return null
        return findNode(root, "0", nodeId)
    }

    fun findFocusedNode(): AccessibilityNodeInfo? =
        service.findFocus(AccessibilityNodeInfo.FOCUS_INPUT)

    private fun findNode(
        node: AccessibilityNodeInfo,
        currentId: String,
        targetId: String
    ): AccessibilityNodeInfo? {
        if (currentId == targetId) return node
        for (index in 0 until node.childCount) {
            val child = node.getChild(index) ?: continue
            val result = findNode(child, "$currentId.$index", targetId)
            if (result != null) return result
        }
        return null
    }

    private fun captureWindow(window: AccessibilityWindowInfo): WindowDto {
        val rect = Rect()
        window.getBoundsInScreen(rect)
        return WindowDto(
            windowId = window.id.toString(),
            packageName = window.root?.packageName?.toString(),
            bounds = rect.toBoundsDto(),
            title = window.title?.toString(),
            isActive = window.isActive,
            isFocused = window.isFocused
        )
    }

    private fun selectCaptureRoot(windows: List<AccessibilityWindowInfo>): AccessibilityNodeInfo? {
        val preferredRoot = windows.firstNotNullOfOrNull { window ->
            val root = window.root ?: return@firstNotNullOfOrNull null
            if (isCompanionPackage(root.packageName?.toString())) null else root
        }
        if (preferredRoot != null) return preferredRoot

        val activeRoot = service.rootInActiveWindow
        return if (activeRoot != null && !isCompanionPackage(activeRoot.packageName?.toString())) {
            activeRoot
        } else {
            null
        }
    }

    private fun captureNode(
        node: AccessibilityNodeInfo,
        nodeId: String,
        windowId: String?
    ): UiNodeDto {
        val rect = Rect()
        node.getBoundsInScreen(rect)
        val children = buildList {
            for (index in 0 until node.childCount) {
                val child = node.getChild(index) ?: continue
                if (isCompanionPackage(child.packageName?.toString())) continue
                add(captureNode(child, "$nodeId.$index", windowId))
            }
        }
        return UiNodeDto(
            nodeId = nodeId,
            windowId = windowId,
            packageName = node.packageName?.toString(),
            className = node.className?.toString(),
            text = node.text?.toString(),
            hintText = node.hintText?.toString(),
            contentDescription = node.contentDescription?.toString(),
            resourceId = node.viewIdResourceName,
            bounds = rect.toBoundsDto(),
            center = CenterDto(rect.centerX(), rect.centerY()),
            clickable = node.isClickable,
            scrollable = node.isScrollable,
            editable = node.isEditable,
            longClickable = if (node.isLongClickable) true else null,
            checkable = if (node.isCheckable) true else null,
            checked = if (node.isChecked) true else null,
            selected = if (node.isSelected) true else null,
            focused = if (node.isFocused) true else null,
            enabled = if (node.isEnabled) null else false,
            visibleToUser = if (node.isVisibleToUser) null else false,
            drawingOrder = node.drawingOrder,
            actionNames = node.actionList.map { it.label?.toString() ?: "action:${it.id}" }
                .takeIf { it.isNotEmpty() },
            children = children
        )
    }

    companion object {
        private const val COMPANION_PACKAGE_NAME = "com.gamehelper.androidcontrol"

        internal fun pruneNodeForSnapshot(node: UiNodeDto): UiNodeDto? {
            if (isCompanionPackageName(node.packageName)) return null
            if (node.visibleToUser == false) return null
            val prunedChildren = node.children.mapNotNull(::pruneNodeForSnapshot)
            return node.copy(
                windowId = null,
                packageName = null,
                drawingOrder = null,
                actionNames = null,
                bounds = null,
                visibleToUser = null,
                children = prunedChildren
            )
        }

        private fun isCompanionPackageName(packageName: String?): Boolean {
            return packageName == COMPANION_PACKAGE_NAME
        }
    }

    private fun pruneNode(node: UiNodeDto): UiNodeDto? {
        return pruneNodeForSnapshot(node)
    }

    private fun Rect.toBoundsDto(): BoundsDto {
        return BoundsDto(left = left, top = top, right = right, bottom = bottom)
    }

    private fun isCompanionWindow(window: AccessibilityWindowInfo): Boolean {
        return isCompanionPackage(window.root?.packageName?.toString())
    }

    private fun isCompanionPackage(packageName: String?): Boolean {
        return isCompanionPackageName(packageName)
    }
}
