package com.aiphone.switchboard

import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.ServiceConnection
import android.os.IBinder
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import net.freehaven.tor.control.TorControlConnection
import org.torproject.jni.TorService
import java.io.File
import kotlin.coroutines.resume

/**
 * Runs the embedded Tor (Guardian Project tor-android), installs the v3 onion
 * client-authorization key and waits until Tor is fully bootstrapped.
 *
 * NOTE: API usage below (TorService / LocalBinder / torControlConnection / getInfo / setConf)
 * follows the tor-android + jtorctl documentation and examples, but this file has NOT been
 * compiled or run by the author. See the "VERIFY" markers.
 */
class TorManager(private val appContext: Context) {

    private val mutex = Mutex()
    private var connection: ServiceConnection? = null
    private var service: TorService? = null          // VERIFY: package org.torproject.jni.TorService
    private var cachedSocks: Pair<String, Int>? = null

    /** True after release(): the UI must reconnect because the local SOCKS port is gone. */
    @Volatile var released: Boolean = false
        private set

    private val authDir: File get() = File(appContext.filesDir, "onion_auth")

    /** Starts Tor (once per process). Returns the local SOCKS5 host and port. */
    suspend fun start(pairing: Pairing, onProgress: (Int) -> Unit): Pair<String, Int> =
        mutex.withLock {
            cachedSocks?.let { onProgress(100); return it }

            val svc = service ?: bind().also { service = it }
            val control = waitForControl(svc)

            installClientAuth(control, pairing)
            val socks = findSocks(control)
            waitForBootstrap(control, onProgress)

            cachedSocks = socks
            released = false
            socks
        }

    /** Removes the key from disk and releases Tor. The process should be killed afterwards. */
    fun stop() {
        authDir.listFiles()?.forEach { it.delete() }
        connection?.let { runCatching { appContext.unbindService(it) } }
        connection = null
        service = null
        cachedSocks = null
    }

    /** Releases Tor (and deletes the key file) after a background poll. The pairing stays stored. */
    suspend fun release() = mutex.withLock {
        authDir.listFiles()?.forEach { it.delete() }
        connection?.let { runCatching { appContext.unbindService(it) } }
        connection = null
        service = null
        cachedSocks = null
        released = true
    }

    // ---- internals -------------------------------------------------------------------------

    private suspend fun bind(): TorService = suspendCancellableCoroutine { cont ->
        val conn = object : ServiceConnection {
            override fun onServiceConnected(name: ComponentName, binder: IBinder) {
                // VERIFY: TorService.LocalBinder#getService()
                if (cont.isActive) cont.resume((binder as TorService.LocalBinder).service)
            }

            override fun onServiceDisconnected(name: ComponentName) {}
        }
        connection = conn
        val ok = appContext.bindService(
            Intent(appContext, TorService::class.java), conn, Context.BIND_AUTO_CREATE
        )
        if (!ok) cont.resumeWith(Result.failure(IllegalStateException("bindService(TorService) failed")))
    }

    private suspend fun waitForControl(svc: TorService): TorControlConnection =
        withContext(Dispatchers.IO) {
            repeat(240) {                                   // up to ~2 minutes
                svc.torControlConnection?.let { return@withContext it }
                delay(500)
            }
            throw IllegalStateException("Tor control connection not available")
        }

    private suspend fun installClientAuth(control: TorControlConnection, p: Pairing) =
        withContext(Dispatchers.IO) {
            val dir = authDir.apply { mkdirs() }
            // owner-only access
            dir.setReadable(false, false); dir.setWritable(false, false); dir.setExecutable(false, false)
            dir.setReadable(true, true); dir.setWritable(true, true); dir.setExecutable(true, true)
            dir.listFiles()?.forEach { it.delete() }

            val f = File(dir, "switchboard.auth_private")
            f.writeText(p.authLine + "\n")
            f.setReadable(false, false); f.setReadable(true, true)

            // VERIFY: assumes Tor loads the *.auth_private files when ClientOnionAuthDir is set
            // at runtime. If the GUI never loads and Tor reports a missing-authorization error,
            // the key must be injected differently (e.g. ONION_CLIENT_AUTH_ADD, base64 key).
            control.setConf("ClientOnionAuthDir", dir.absolutePath)
        }

    private suspend fun findSocks(control: TorControlConnection): Pair<String, Int> =
        withContext(Dispatchers.IO) {
            val re = Regex("""(\d{1,3}(?:\.\d{1,3}){3}):(\d+)""")
            fun read(): Pair<String, Int>? {
                val raw = runCatching { control.getInfo("net/listeners/socks") }.getOrNull().orEmpty()
                val m = re.find(raw) ?: return null
                return m.groupValues[1] to m.groupValues[2].toInt()
            }
            read()?.let { return@withContext it }

            // No SOCKS listener configured: ask Tor for a free port on localhost.
            control.setConf("SocksPort", "127.0.0.1:auto")
            repeat(40) {
                read()?.let { return@withContext it }
                delay(250)
            }
            throw IllegalStateException("Tor SOCKS listener not available")
        }

    private suspend fun waitForBootstrap(control: TorControlConnection, onProgress: (Int) -> Unit) =
        withContext(Dispatchers.IO) {
            val re = Regex("PROGRESS=(\\d+)")
            repeat(600) {                                   // up to ~5 minutes
                val s = runCatching { control.getInfo("status/bootstrap-phase") }.getOrNull().orEmpty()
                val pct = re.find(s)?.groupValues?.get(1)?.toIntOrNull() ?: 0
                onProgress(pct)
                if (pct >= 100) return@withContext
                delay(500)
            }
            throw IllegalStateException("Tor bootstrap timed out")
        }
}
