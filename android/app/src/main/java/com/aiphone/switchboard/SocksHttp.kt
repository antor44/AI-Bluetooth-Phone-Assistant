package com.aiphone.switchboard

import java.io.ByteArrayOutputStream
import java.io.DataInputStream
import java.io.IOException
import java.net.InetSocketAddress
import java.net.Socket

/**
 * Minimal HTTP GET through a local SOCKS5 proxy (Tor). The onion host name is sent to the proxy as a
 * domain name (SOCKS5 ATYP 0x03), so it is never resolved on the phone.
 */
object SocksHttp {

    fun get(
        socksHost: String, socksPort: Int, targetHost: String, targetPort: Int,
        path: String, timeoutMs: Int = 120_000
    ): String {
        Socket().use { socket ->
            socket.soTimeout = timeoutMs
            socket.connect(InetSocketAddress(socksHost, socksPort), 10_000)
            val out = socket.getOutputStream()
            val inp = DataInputStream(socket.getInputStream())

            // Greeting: version 5, one method, "no authentication".
            out.write(byteArrayOf(5, 1, 0)); out.flush()
            val method = ByteArray(2); inp.readFully(method)
            if (method[0] != 5.toByte() || method[1] != 0.toByte()) throw IOException("SOCKS5 handshake rejected")

            // CONNECT request with a domain name.
            val hostBytes = targetHost.toByteArray(Charsets.US_ASCII)
            val req = ByteArrayOutputStream()
            req.write(byteArrayOf(5, 1, 0, 3, hostBytes.size.toByte()))
            req.write(hostBytes)
            req.write(targetPort shr 8); req.write(targetPort and 0xFF)
            out.write(req.toByteArray()); out.flush()

            val head = ByteArray(4); inp.readFully(head)
            if (head[1] != 0.toByte()) throw IOException("SOCKS5 connect failed (code ${head[1].toInt() and 0xFF})")
            val boundLen = when (head[3].toInt()) {
                1 -> 4
                3 -> inp.readUnsignedByte()
                4 -> 16
                else -> throw IOException("SOCKS5 unknown address type")
            }
            inp.readFully(ByteArray(boundLen + 2))          // bound address + port, ignored

            val request = "GET $path HTTP/1.0\r\nHost: $targetHost\r\nAccept: application/json\r\n" +
                "Connection: close\r\n\r\n"
            out.write(request.toByteArray(Charsets.US_ASCII)); out.flush()

            val raw = inp.readBytes().toString(Charsets.UTF_8)
            val split = raw.indexOf("\r\n\r\n")
            if (split < 0) throw IOException("Malformed HTTP response")
            val statusLine = raw.substring(0, raw.indexOf("\r\n"))
            if (!statusLine.contains(" 200")) throw IOException("HTTP error: $statusLine")
            return raw.substring(split + 4)
        }
    }
}
