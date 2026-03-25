package com.gamehelper.androidcontrol.model

object UiNodeQueryEngine {

    fun findMatches(nodes: List<UiNodeDto>, query: NodeQueryDto): List<UiNodeDto> {
        return flatten(nodes).filter { matches(it, query) }
    }

    fun findMatchesEnriched(
        root: UiNodeDto,
        query: NodeQueryDto,
        nodesById: Map<String, UiNodeDto>,
        currentPackage: String?
    ): FindNodesResultDto {
        val matched = flatten(listOf(root)).filter { matches(it, query) }
        val items = matched.map { node ->
            val matchScore = computeMatchScore(node, query)
            val parentHint = buildParentHint(node.nodeId, nodesById)
            val siblingTexts = buildSiblingTexts(node.nodeId, nodesById)
            val resolvedClick = resolveClickTarget(node, nodesById)
            FindNodeResultItemDto(
                nodeId = node.nodeId,
                text = node.text,
                contentDescription = node.contentDescription,
                resourceId = node.resourceId,
                clickable = node.clickable,
                center = node.center,
                matchScore = matchScore,
                parentHint = parentHint,
                siblingTexts = siblingTexts.takeIf { it.isNotEmpty() },
                resolvedClick = resolvedClick
            )
        }
        return FindNodesResultDto(
            currentPackage = currentPackage,
            totalMatches = items.size,
            nodes = items
        )
    }

    fun resolveClickTarget(node: UiNodeDto, nodesById: Map<String, UiNodeDto>): ResolvedClickDto {
        if (node.clickable) {
            val center = node.center ?: return ResolvedClickDto("coordinate", null, CenterDto(0, 0))
            return ResolvedClickDto("self", node.nodeId, center)
        }
        var currentId = node.nodeId
        while (currentId.contains('.')) {
            currentId = currentId.substringBeforeLast('.')
            val parent = nodesById[currentId]
            if (parent?.clickable == true) {
                val center = parent.center ?: continue
                return ResolvedClickDto("ancestor", currentId, center)
            }
        }
        val center = node.center ?: CenterDto(0, 0)
        return ResolvedClickDto("coordinate", null, center)
    }

    private fun computeMatchScore(node: UiNodeDto, query: NodeQueryDto): String {
        return if (query.text != null &&
            (node.text == query.text || node.contentDescription == query.text)
        ) "exact" else "contains"
    }

    private fun buildParentHint(nodeId: String, nodesById: Map<String, UiNodeDto>): String? {
        val parts = mutableListOf<String>()
        var currentId = nodeId
        var levels = 0
        while (currentId.contains('.') && levels < 3) {
            currentId = currentId.substringBeforeLast('.')
            val parent = nodesById[currentId] ?: break
            val simpleName = parent.className?.substringAfterLast('.') ?: "View"
            parts.add(0, simpleName)
            levels++
        }
        return if (parts.isEmpty()) null else parts.joinToString(" > ")
    }

    private fun buildSiblingTexts(nodeId: String, nodesById: Map<String, UiNodeDto>): List<String> {
        if (!nodeId.contains('.')) return emptyList()
        val parentId = nodeId.substringBeforeLast('.')
        val parent = nodesById[parentId] ?: return emptyList()
        return parent.children
            .filter { it.nodeId != nodeId }
            .mapNotNull { child ->
                (child.text?.takeIf { it.isNotBlank() }
                    ?: child.contentDescription?.takeIf { it.isNotBlank() })
            }
            .take(5)
    }

    private fun flatten(nodes: List<UiNodeDto>): List<UiNodeDto> {
        val output = mutableListOf<UiNodeDto>()
        for (node in nodes) {
            output += node
            output += flatten(node.children)
        }
        return output
    }

    private fun matches(node: UiNodeDto, query: NodeQueryDto): Boolean {
        if (query.text != null &&
            node.text != query.text &&
            node.contentDescription != query.text
        ) return false
        if (query.textContains != null) {
            val textMatch = node.text?.contains(query.textContains, ignoreCase = true) == true
            val descMatch = node.contentDescription?.contains(query.textContains, ignoreCase = true) == true
            if (!textMatch && !descMatch) return false
        }
        if (query.resourceId != null && node.resourceId != query.resourceId) return false
        if (query.className != null && node.className != query.className) return false
        // Skip packageName check when node.packageName is null (pruned tree)
        if (query.packageName != null && node.packageName != null &&
            node.packageName != query.packageName
        ) return false
        if (query.clickable != null && node.clickable != query.clickable) return false
        return true
    }
}
