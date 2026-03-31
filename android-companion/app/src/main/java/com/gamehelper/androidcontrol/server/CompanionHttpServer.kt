package com.gamehelper.androidcontrol.server

import com.gamehelper.androidcontrol.actions.GestureExecutor
import com.gamehelper.androidcontrol.actions.NodeActionExecutor
import com.gamehelper.androidcontrol.capture.HierarchyCaptureManager
import com.gamehelper.androidcontrol.model.CompanionStatusDto
import com.gamehelper.androidcontrol.model.DoubleTapRequestDto
import com.gamehelper.androidcontrol.model.FindNodesResultDto
import com.gamehelper.androidcontrol.model.LongPressRequestDto
import com.gamehelper.androidcontrol.model.NodeActionRequestDto
import com.gamehelper.androidcontrol.model.NodeQueryDto
import com.gamehelper.androidcontrol.model.ScreenContextDto
import com.gamehelper.androidcontrol.model.ScreenContextNodeDto
import com.gamehelper.androidcontrol.model.SetTextRequestDto
import com.gamehelper.androidcontrol.model.SwipeRequestDto
import com.gamehelper.androidcontrol.model.UiNodeDto
import com.gamehelper.androidcontrol.model.UiNodeQueryEngine
import com.gamehelper.androidcontrol.store.SnapshotStore
import com.google.gson.Gson
import java.io.ByteArrayOutputStream
import java.net.InetAddress
import java.net.ServerSocket
import java.net.Socket
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

class CompanionHttpServer(
    private val port: Int,
    private val snapshotStore: SnapshotStore,
    private val captureManager: HierarchyCaptureManager,
    private val nodeActionExecutor: NodeActionExecutor,
    private val gestureExecutor: GestureExecutor,
    private val statusProvider: () -> CompanionStatusDto,
    private val webSocketServer: CompanionWebSocketServer,
    private val gson: Gson = Gson()
) {

    private val running = AtomicBoolean(false)
    private val executor = Executors.newCachedThreadPool()
    private var serverSocket: ServerSocket? = null

    fun start() {
        if (!running.compareAndSet(false, true)) return
        serverSocket = ServerSocket(port, 50, InetAddress.getByName("127.0.0.1"))
        executor.execute {
            while (running.get()) {
                val socket = try {
                    serverSocket?.accept()
                } catch (_: Exception) {
                    null
                } ?: continue
                executor.execute { handle(socket) }
            }
        }
    }

    fun stop() {
        running.set(false)
        runCatching { serverSocket?.close() }
        executor.shutdownNow()
    }

    private fun handle(socket: Socket) {
        socket.use {
            val request = readRequest(it) ?: return
            val response = when {
                request.method == "GET" && request.path == "/status" -> {
                    Response(200, gson.toJson(statusProvider()))
                }

                request.method == "POST" && request.path == "/session/start" -> {
                    captureManager.captureLatest()
                    Response(200, gson.toJson(statusProvider()))
                }

                request.method == "POST" && request.path == "/ui/tree" -> {
                    val snapshot = captureManager.captureWithCache() ?: snapshotStore.getSnapshot()
                    Response(200, gson.toJson(snapshot))
                }

                request.method == "POST" && request.path == "/nodes/search" -> {
                    val query = gson.fromJson(request.body, NodeQueryDto::class.java)
                    val snapshot = captureManager.captureWithCache(300) ?: snapshotStore.getSnapshot()
                    val root = snapshot?.root
                    val currentPackage = snapshot?.packageName
                    val nodesById = snapshotStore.getNodesById()
                    val result = if (root != null) {
                        UiNodeQueryEngine.findMatchesEnriched(root, query, nodesById, currentPackage)
                    } else {
                        FindNodesResultDto(
                            currentPackage = currentPackage,
                            totalMatches = 0,
                            nodes = emptyList()
                        )
                    }
                    Response(200, gson.toJson(result))
                }

                request.method == "POST" && request.path == "/actions/click-node" -> {
                    val clickRequest = gson.fromJson(request.body, NodeActionRequestDto::class.java)
                    val success = nodeActionExecutor.clickNode(clickRequest)
                    Response(200, gson.toJson(mapOf("source" to "companion", "success" to success)))
                }

                request.method == "POST" && request.path == "/actions/set-text" -> {
                    val payload = gson.fromJson(request.body, SetTextRequestDto::class.java)
                    val success = if (payload.nodeId != null) {
                        nodeActionExecutor.setText(payload.nodeId, payload.text)
                    } else {
                        nodeActionExecutor.setTextOnFocused(payload.text)
                    }
                    Response(200, gson.toJson(mapOf("success" to success)))
                }

                request.method == "POST" && request.path == "/actions/tap" -> {
                    val payload = gson.fromJson(request.body, TapRequest::class.java)
                    val success = gestureExecutor.tap(payload.x, payload.y)
                    Response(200, gson.toJson(mapOf("source" to "companion", "success" to success)))
                }

                request.method == "POST" && request.path == "/actions/swipe" -> {
                    val payload = gson.fromJson(request.body, SwipeRequestDto::class.java)
                    val success = gestureExecutor.swipe(
                        payload.startX,
                        payload.startY,
                        payload.endX,
                        payload.endY,
                        payload.durationMs
                    )
                    Response(200, gson.toJson(mapOf("source" to "companion", "success" to success)))
                }

                request.method == "POST" && request.path == "/actions/double-tap" -> {
                    val payload = gson.fromJson(request.body, DoubleTapRequestDto::class.java)
                    val success = gestureExecutor.doubleTap(payload.x, payload.y, payload.intervalMs)
                    Response(200, gson.toJson(mapOf("source" to "companion", "success" to success)))
                }

                request.method == "POST" && request.path == "/actions/long-press" -> {
                    val payload = gson.fromJson(request.body, LongPressRequestDto::class.java)
                    val success = gestureExecutor.longPress(payload.x, payload.y, payload.durationMs)
                    Response(200, gson.toJson(mapOf("source" to "companion", "success" to success)))
                }

                request.method == "POST" && request.path == "/actions/back" -> {
                    val success = gestureExecutor.pressBack()
                    Response(200, gson.toJson(mapOf("source" to "companion", "success" to success)))
                }

                request.method == "POST" && request.path == "/actions/home" -> {
                    val success = gestureExecutor.pressHome()
                    Response(200, gson.toJson(mapOf("source" to "companion", "success" to success)))
                }

                request.method == "GET" && request.path == "/screen/context" -> {
                    val snapshot = snapshotStore.getSnapshot()
                    val nodesById = snapshotStore.getNodesById()
                    val allNodes = nodesById.values.toList()
                    val currentPackage = snapshot?.packageName
                    val title = snapshot?.windows?.firstOrNull { it.isFocused }?.title
                        ?: snapshot?.windows?.firstOrNull { it.isActive }?.title

                    val clickableNodes = allNodes
                        .filter { (it.clickable || it.scrollable) && hasLabel(it) }
                        .take(20)
                        .map { node ->
                            ScreenContextNodeDto(
                                text = node.text ?: node.contentDescription,
                                resourceId = node.resourceId?.substringAfterLast('/'),
                                center = node.center,
                                hint = buildParentHint(node.nodeId, nodesById)
                            )
                        }

                    val editableNodes = allNodes
                        .filter { it.editable }
                        .take(5)
                        .map { node ->
                            ScreenContextNodeDto(
                                text = node.text,
                                hintText = node.hintText,
                                desc = node.contentDescription,
                                resourceId = node.resourceId?.substringAfterLast('/'),
                                center = node.center,
                                hint = buildParentHint(node.nodeId, nodesById)
                            )
                        }

                    val context = ScreenContextDto(
                        packageName = currentPackage,
                        title = title,
                        clickableNodes = clickableNodes,
                        editableNodes = editableNodes
                    )
                    Response(200, gson.toJson(context))
                }

                else -> Response(404, gson.toJson(mapOf("error" to "Not found")))
            }

            writeResponse(it, response)
        }
    }

    private fun hasLabel(node: UiNodeDto): Boolean =
        !node.text.isNullOrBlank() || !node.contentDescription.isNullOrBlank()

    private fun buildParentHint(nodeId: String, nodesById: Map<String, UiNodeDto>): String? {
        val parts = mutableListOf<String>()
        var currentId = nodeId
        var levels = 0
        while (currentId.contains('.') && levels < 2) {
            currentId = currentId.substringBeforeLast('.')
            val parent = nodesById[currentId] ?: break
            val simpleName = parent.className?.substringAfterLast('.') ?: "View"
            parts.add(0, simpleName)
            levels++
        }
        return if (parts.isEmpty()) null else parts.joinToString(" > ")
    }

    private fun readRequest(socket: Socket): Request? {
        val input = socket.getInputStream()
        val headerBytes = ByteArrayOutputStream()
        var matched = 0
        headerLoop@ while (true) {
            val byte = input.read()
            if (byte == -1) return null
            headerBytes.write(byte)
            when {
                matched == 0 && byte == '\r'.code -> matched = 1
                matched == 1 && byte == '\n'.code -> matched = 2
                matched == 2 && byte == '\r'.code -> matched = 3
                matched == 3 && byte == '\n'.code -> break@headerLoop
                else -> matched = 0
            }
        }

        val headerText = headerBytes.toString(Charsets.UTF_8.name())
        val lines = headerText.split("\r\n").filter { it.isNotBlank() }
        if (lines.isEmpty()) return null
        val requestLine = lines.first().split(" ")
        if (requestLine.size < 2) return null

        val headers = lines.drop(1).associate {
            val parts = it.split(":", limit = 2)
            parts[0].trim().lowercase() to parts.getOrElse(1) { "" }.trim()
        }

        val bodyLength = headers["content-length"]?.toIntOrNull() ?: 0
        val bodyBytes = ByteArray(bodyLength)
        var read = 0
        while (read < bodyLength) {
            val current = input.read(bodyBytes, read, bodyLength - read)
            if (current == -1) break
            read += current
        }

        return Request(
            method = requestLine[0],
            path = requestLine[1].substringBefore("?"),
            body = String(bodyBytes, 0, read, Charsets.UTF_8)
        )
    }

    private fun writeResponse(socket: Socket, response: Response) {
        val body = response.body.toByteArray(Charsets.UTF_8)
        val headers = buildString {
            append("HTTP/1.1 ${response.status} ${statusText(response.status)}\r\n")
            append("Content-Type: application/json; charset=utf-8\r\n")
            append("Content-Length: ${body.size}\r\n")
            append("Connection: close\r\n")
            append("\r\n")
        }.toByteArray(Charsets.UTF_8)

        socket.getOutputStream().write(headers)
        socket.getOutputStream().write(body)
        socket.getOutputStream().flush()
    }

    private fun statusText(status: Int): String {
        return when (status) {
            200 -> "OK"
            404 -> "Not Found"
            else -> "Server Error"
        }
    }

    private data class Request(
        val method: String,
        val path: String,
        val body: String
    )

    private data class Response(
        val status: Int,
        val body: String
    )

    private data class TapRequest(
        val x: Int,
        val y: Int
    )
}
