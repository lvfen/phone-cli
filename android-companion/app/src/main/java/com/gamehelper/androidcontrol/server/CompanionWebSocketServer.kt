package com.gamehelper.androidcontrol.server

import com.gamehelper.androidcontrol.model.UiSnapshotDto
import com.google.gson.Gson
import java.io.BufferedReader
import java.io.InputStreamReader
import java.net.InetAddress
import java.net.ServerSocket
import java.net.Socket
import java.security.MessageDigest
import java.util.Base64
import java.util.Collections
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

class CompanionWebSocketServer(
    private val port: Int,
    private val gson: Gson = Gson()
) {

    private val running = AtomicBoolean(false)
    private val executor = Executors.newCachedThreadPool()
    private val clients = Collections.synchronizedSet(mutableSetOf<Socket>())
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
                executor.execute { handleSocket(socket) }
            }
        }
    }

    fun stop() {
        running.set(false)
        clients.forEach {
            runCatching { it.close() }
        }
        clients.clear()
        runCatching { serverSocket?.close() }
        executor.shutdownNow()
    }

    fun broadcastSnapshot(snapshot: UiSnapshotDto) {
        broadcastJson(
            gson.toJson(
                mapOf(
                    "type" to "snapshot",
                    "payload" to snapshot
                )
            )
        )
    }

    private fun handleSocket(socket: Socket) {
        try {
            val reader = BufferedReader(InputStreamReader(socket.getInputStream()))
            val requestLine = reader.readLine() ?: return
            if (!requestLine.startsWith("GET")) return

            var websocketKey: String? = null
            while (true) {
                val line = reader.readLine() ?: break
                if (line.isBlank()) break
                val parts = line.split(":", limit = 2)
                if (parts.size == 2 && parts[0].equals("Sec-WebSocket-Key", ignoreCase = true)) {
                    websocketKey = parts[1].trim()
                }
            }

            val accept = buildAcceptKey(websocketKey ?: return)
            val response = buildString {
                append("HTTP/1.1 101 Switching Protocols\r\n")
                append("Upgrade: websocket\r\n")
                append("Connection: Upgrade\r\n")
                append("Sec-WebSocket-Accept: $accept\r\n")
                append("\r\n")
            }
            socket.getOutputStream().write(response.toByteArray(Charsets.UTF_8))
            socket.getOutputStream().flush()
            clients += socket
        } catch (_: Exception) {
            runCatching { socket.close() }
        }
    }

    private fun broadcastJson(message: String) {
        val payload = message.toByteArray(Charsets.UTF_8)
        val frame = encodeTextFrame(payload)
        val stale = mutableListOf<Socket>()
        synchronized(clients) {
            clients.forEach { socket ->
                val success = runCatching {
                    socket.getOutputStream().write(frame)
                    socket.getOutputStream().flush()
                }.isSuccess
                if (!success) stale += socket
            }
            stale.forEach {
                clients.remove(it)
                runCatching { it.close() }
            }
        }
    }

    private fun buildAcceptKey(websocketKey: String): String {
        val source = "${websocketKey}258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
        val digest = MessageDigest.getInstance("SHA-1").digest(source.toByteArray(Charsets.UTF_8))
        return Base64.getEncoder().encodeToString(digest)
    }

    private fun encodeTextFrame(payload: ByteArray): ByteArray {
        val len = payload.size
        return when {
            len < 126 -> byteArrayOf(0x81.toByte(), len.toByte()) + payload
            len < 65536 -> byteArrayOf(
                0x81.toByte(),
                126.toByte(),
                ((len shr 8) and 0xFF).toByte(),
                (len and 0xFF).toByte()
            ) + payload
            else -> {
                val lenLong = len.toLong()
                byteArrayOf(
                    0x81.toByte(),
                    127.toByte(),
                    ((lenLong shr 56) and 0xFF).toByte(),
                    ((lenLong shr 48) and 0xFF).toByte(),
                    ((lenLong shr 40) and 0xFF).toByte(),
                    ((lenLong shr 32) and 0xFF).toByte(),
                    ((lenLong shr 24) and 0xFF).toByte(),
                    ((lenLong shr 16) and 0xFF).toByte(),
                    ((lenLong shr 8) and 0xFF).toByte(),
                    (lenLong and 0xFF).toByte()
                ) + payload
            }
        }
    }
}
