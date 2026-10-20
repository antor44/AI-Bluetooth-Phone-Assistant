package com.aiphone.switchboard

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.withContext
import org.json.JSONObject

/**
 * Periodic poll (every ~15 min) of the switchboard's notification endpoint through Tor.
 * Starts Tor if it is not running, asks for items newer than the stored cursors, shows one
 * notification per item and, when the app is not on screen, releases Tor again to save battery.
 *
 * NOTE: not compiled or run by the author of this change. See the "VERIFY" markers.
 */
class PollWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {

    companion object {
        /** Must match 'tor_notify_port' in the daemon (default 8502). */
        const val NOTIFY_PORT = 8502
        /** Set to false to keep Tor bound after each poll (faster, but uses more battery). */
        const val RELEASE_TOR_AFTER_POLL = true
    }

    override suspend fun doWork(): Result {
        val app = applicationContext as App
        val prefs = NotifyPrefs(applicationContext)
        val pairing = PairingStore(applicationContext).load()
        if (!prefs.enabled || pairing == null) return Result.success()

        return try {
            val (host, port) = app.tor.start(pairing) { }

            val query = buildString {
                append("/api/events")
                if (prefs.lastMessageId >= 0 && prefs.lastCallId >= 0) {
                    append("?since_message=").append(prefs.lastMessageId)
                    append("&since_call=").append(prefs.lastCallId)
                }
            }
            val body = withContext(Dispatchers.IO) {
                SocksHttp.get(host, port, pairing.onion, NOTIFY_PORT, query)
            }
            val json = JSONObject(body)

            val messages = json.getJSONArray("messages")
            for (i in 0 until messages.length()) {
                val m = messages.getJSONObject(i)
                val who = m.optString("caller").ifBlank { applicationContext.getString(R.string.notify_unknown_caller) }
                Notifications.show(
                    applicationContext, 1_000_000 + m.getInt("id"),
                    applicationContext.getString(R.string.notify_new_message, who), m.optString("text")
                )
            }
            val calls = json.getJSONArray("calls")
            for (i in 0 until calls.length()) {
                val c = calls.getJSONObject(i)
                val who = c.optString("caller").ifBlank { applicationContext.getString(R.string.notify_unknown_caller) }
                Notifications.show(
                    applicationContext, 2_000_000 + c.getInt("id"),
                    applicationContext.getString(R.string.notify_new_call, who), c.optString("summary")
                )
            }

            // Cursors are saved only after the items were shown.
            prefs.lastMessageId = json.getLong("max_message_id")
            prefs.lastCallId = json.getLong("max_call_id")
            Result.success()
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            if (runAttemptCount < 2) Result.retry() else Result.success()
        } finally {
            if (RELEASE_TOR_AFTER_POLL && app.startedActivities.get() == 0) {
                withContext(NonCancellable) { app.tor.release() }
            }
        }
    }
}
