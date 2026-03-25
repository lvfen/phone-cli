package com.gamehelper.androidcontrol.store

import com.gamehelper.androidcontrol.model.UiNodeDto
import com.gamehelper.androidcontrol.model.UiSnapshotDto
import java.util.concurrent.atomic.AtomicReference

class SnapshotStore {

    private val snapshotRef = AtomicReference<UiSnapshotDto?>(null)
    private val nodesById = LinkedHashMap<String, UiNodeDto>()

    @Synchronized
    fun update(snapshot: UiSnapshotDto) {
        snapshotRef.set(snapshot)
        nodesById.clear()
        snapshot.root?.let { indexNode(it) }
    }

    fun getSnapshot(): UiSnapshotDto? = snapshotRef.get()

    @Synchronized
    fun findNodeById(nodeId: String): UiNodeDto? = nodesById[nodeId]

    @Synchronized
    fun flattenNodes(): List<UiNodeDto> = nodesById.values.toList()

    @Synchronized
    fun getNodesById(): Map<String, UiNodeDto> = LinkedHashMap(nodesById)

    private fun indexNode(node: UiNodeDto) {
        nodesById[node.nodeId] = node
        node.children.forEach(::indexNode)
    }
}
