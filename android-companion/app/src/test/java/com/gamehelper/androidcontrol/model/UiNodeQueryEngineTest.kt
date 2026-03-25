package com.gamehelper.androidcontrol.model

import org.junit.Assert.assertEquals
import org.junit.Test

class UiNodeQueryEngineTest {

    @Test
    fun findMatchesFiltersByTextAndClickability() {
        val nodes = listOf(
            UiNodeDto(
                nodeId = "root",
                className = "android.widget.FrameLayout",
                children = listOf(
                    UiNodeDto(
                        nodeId = "login_button",
                        text = "登录",
                        clickable = true
                    ),
                    UiNodeDto(
                        nodeId = "help_button",
                        text = "帮助",
                        clickable = false
                    )
                )
            )
        )

        val matches = UiNodeQueryEngine.findMatches(
            nodes = nodes,
            query = NodeQueryDto(text = "登录", clickable = true)
        )

        assertEquals(listOf("login_button"), matches.map { it.nodeId })
    }
}
