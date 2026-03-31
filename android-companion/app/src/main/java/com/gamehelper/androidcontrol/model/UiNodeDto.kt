package com.gamehelper.androidcontrol.model

data class BoundsDto(
    val left: Int,
    val top: Int,
    val right: Int,
    val bottom: Int
)

data class CenterDto(
    val x: Int,
    val y: Int
)

data class WindowDto(
    val windowId: String,
    val packageName: String? = null,
    val bounds: BoundsDto? = null,
    val title: String? = null,
    val isActive: Boolean = false,
    val isFocused: Boolean = false
)

data class UiNodeDto(
    val nodeId: String,
    val windowId: String? = null,
    val packageName: String? = null,
    val className: String? = null,
    val text: String? = null,
    val hintText: String? = null,
    val contentDescription: String? = null,
    val resourceId: String? = null,
    val bounds: BoundsDto? = null,
    val center: CenterDto? = null,
    // Important interactive flags — kept as non-nullable, always serialized
    val clickable: Boolean = false,
    val scrollable: Boolean = false,
    val editable: Boolean = false,
    // Noisy flags — nullable: null means false (omitted from JSON by Gson)
    val longClickable: Boolean? = null,
    val checkable: Boolean? = null,
    val checked: Boolean? = null,
    val selected: Boolean? = null,
    val focused: Boolean? = null,
    // enabled: null means true (omitted), false means explicitly disabled
    val enabled: Boolean? = null,
    // visibleToUser: null means true (omitted), false means not visible (used for pruning)
    val visibleToUser: Boolean? = null,
    val drawingOrder: Int? = null,
    val actionNames: List<String>? = null,
    val children: List<UiNodeDto> = emptyList()
)

data class UiSnapshotDto(
    val capturedAt: String,
    val packageName: String? = null,
    val windows: List<WindowDto>,
    val root: UiNodeDto?
)

data class NodeQueryDto(
    val text: String? = null,
    val textContains: String? = null,
    val resourceId: String? = null,
    val className: String? = null,
    val packageName: String? = null,
    val clickable: Boolean? = null
)

data class NodeActionRequestDto(
    val deviceId: String? = null,
    val nodeId: String,
    val fallbackBounds: FallbackBoundsDto? = null
)

data class FallbackBoundsDto(
    val centerX: Int,
    val centerY: Int
)

data class SwipeRequestDto(
    val startX: Int,
    val startY: Int,
    val endX: Int,
    val endY: Int,
    val durationMs: Long = 250L
)

data class CompanionStatusDto(
    val ready: Boolean,
    val serviceConnected: Boolean,
    val lastCaptureAt: String? = null,
    val packageName: String? = null
)

data class SetTextRequestDto(
    val nodeId: String? = null,
    val text: String
)

data class ResolvedClickDto(
    val type: String,        // "self" | "ancestor" | "coordinate"
    val nodeId: String? = null,
    val center: CenterDto
)

data class FindNodeResultItemDto(
    val nodeId: String,
    val text: String? = null,
    val contentDescription: String? = null,
    val resourceId: String? = null,
    val clickable: Boolean = false,
    val center: CenterDto? = null,
    val matchScore: String,   // "exact" | "contains"
    val parentHint: String? = null,
    val siblingTexts: List<String>? = null,
    val resolvedClick: ResolvedClickDto
)

data class FindNodesResultDto(
    val currentPackage: String? = null,
    val totalMatches: Int,
    val nodes: List<FindNodeResultItemDto>
)

data class ScreenContextNodeDto(
    val text: String? = null,
    val hintText: String? = null,
    val desc: String? = null,
    val resourceId: String? = null,
    val center: CenterDto? = null,
    val hint: String? = null
)

data class ScreenContextDto(
    val packageName: String? = null,
    val title: String? = null,
    val clickableNodes: List<ScreenContextNodeDto> = emptyList(),
    val editableNodes: List<ScreenContextNodeDto> = emptyList()
)

data class DoubleTapRequestDto(
    val x: Int,
    val y: Int,
    val intervalMs: Long = 100L
)

data class LongPressRequestDto(
    val x: Int,
    val y: Int,
    val durationMs: Long = 3000L
)
