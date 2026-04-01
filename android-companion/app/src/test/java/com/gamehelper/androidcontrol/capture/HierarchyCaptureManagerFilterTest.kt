package com.gamehelper.androidcontrol.capture

import com.gamehelper.androidcontrol.model.BoundsDto
import com.gamehelper.androidcontrol.model.CenterDto
import com.gamehelper.androidcontrol.model.UiNodeDto
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Test

class HierarchyCaptureManagerFilterTest {

    @Test
    fun pruneNodeRemovesCompanionPackageChildren() {
        val root = UiNodeDto(
            nodeId = "0",
            packageName = "com.target.app",
            className = "android.widget.FrameLayout",
            bounds = BoundsDto(0, 0, 100, 200),
            center = CenterDto(50, 100),
            children = listOf(
                UiNodeDto(
                    nodeId = "0.0",
                    packageName = "com.target.app",
                    text = "发布",
                    clickable = true,
                    bounds = BoundsDto(0, 0, 50, 50),
                    center = CenterDto(25, 25)
                ),
                UiNodeDto(
                    nodeId = "0.1",
                    packageName = "com.gamehelper.androidcontrol",
                    text = "稳",
                    clickable = true,
                    bounds = BoundsDto(90, 20, 100, 80),
                    center = CenterDto(95, 50)
                )
            )
        )

        val filtered = HierarchyCaptureManager.pruneNodeForSnapshot(root)

        assertNotNull(filtered)
        assertEquals(1, filtered!!.children.size)
        assertEquals("发布", filtered.children.first().text)
        assertFalse(filtered.children.any { it.packageName == "com.gamehelper.androidcontrol" })
    }
}
