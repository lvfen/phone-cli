package com.gamehelper.androidcontrol.store

import com.gamehelper.androidcontrol.model.BoundsDto
import com.gamehelper.androidcontrol.model.CenterDto
import com.gamehelper.androidcontrol.model.UiNodeDto
import com.gamehelper.androidcontrol.model.UiSnapshotDto
import com.gamehelper.androidcontrol.model.WindowDto
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Test

class SnapshotStoreTest {

    @Test
    fun updateIndexesAllNodesById() {
        val store = SnapshotStore()
        val snapshot = UiSnapshotDto(
            capturedAt = "2026-03-20T00:00:00Z",
            windows = listOf(
                WindowDto(
                    windowId = "main",
                    packageName = "com.demo.app",
                    bounds = BoundsDto(0, 0, 1080, 2400),
                    isActive = true
                )
            ),
            root = UiNodeDto(
                nodeId = "root",
                packageName = "com.demo.app",
                className = "android.widget.FrameLayout",
                bounds = BoundsDto(0, 0, 1080, 2400),
                center = CenterDto(540, 1200),
                children = listOf(
                    UiNodeDto(
                        nodeId = "login_button",
                        text = "登录",
                        clickable = true,
                        bounds = BoundsDto(100, 200, 400, 280),
                        center = CenterDto(250, 240)
                    )
                )
            )
        )

        store.update(snapshot)

        assertNotNull(store.findNodeById("login_button"))
        assertEquals(2, store.flattenNodes().size)
    }
}
