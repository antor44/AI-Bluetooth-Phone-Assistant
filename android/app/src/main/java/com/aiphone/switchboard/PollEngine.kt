package com.aiphone.switchboard

import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import org.json.JSONObject

/**
 * One request to the switchboard's notification endpoint through Tor, shared by the periodic job and
 * the foreground service. A lock makes sure two callers never run at once, so the stored cursors are
 * always up to date and no item is notified twice.
 */
object PollEngine {
    private val lock = Mutex()

    /** Result of one poll: how many notifications were shown. */
    data class Outcome(val itemCount: Int)

    /**
     * @param waitSeconds when above 0 (and the cursors are known) the switchboard may hold the request
     * open until something new exists. An older switchboard ignores it and answers at once.
     */
    suspend fun pollOnce(context: Context, waitSeconds: Int = 0): Outcome = lock.withLock {
        val appContext = context.applicationContext
        val app = appContext as App
        val prefs = NotifyPrefs(appContext)
        val pairing = PairingStore(appContext).load() ?: return@withLock Outcome(0)

        val (host, port) = app.tor.start(pairing) { }

        val hasCursors = prefs.lastMessageId >= 0 && prefs.lastCallId >= 0
        val query = buildString {
            append(AppConfig.NOTIFY_PATH)
            if (hasCursors) {
                append("?since_message=").append(prefs.lastMessageId)
                append("&since_call=").append(prefs.lastCallId)
                if (waitSeconds > 0) append("&wait=").append(waitSeconds)
            }
        }
        val timeoutMs = if (hasCursors && waitSeconds > 0) {
            (waitSeconds + AppConfig.HTTP_TIMEOUT_MARGIN_SECONDS) * 1000
        } else {
            AppConfig.HTTP_TIMEOUT_DEFAULT_MS
        }
        val body = withContext(Dispatchers.IO) {
            SocksHttp.get(host, port, pairing.onion, AppConfig.NOTIFY_PORT, query, timeoutMs)
        }
        val json = JSONObject(body)
        val unknownCaller = appContext.getString(R.string.notify_unknown_caller)

        var lastShownMessageId = -1L
        val messages = json.getJSONArray("messages")
        for (i in 0 until messages.length()) {
            val m = messages.getJSONObject(i)
            val who = m.optString("caller").ifBlank { unknownCaller }
            val id = m.getLong("id")
            Notifications.show(
                appContext, AppConfig.NOTIFICATION_ID_MESSAGE_BASE + id.toInt(),
                appContext.getString(R.string.notify_new_message, who), m.optString("text")
            )
            lastShownMessageId = maxOf(lastShownMessageId, id)
        }
        var lastShownCallId = -1L
        val calls = json.getJSONArray("calls")
        for (i in 0 until calls.length()) {
            val c = calls.getJSONObject(i)
            val who = c.optString("caller").ifBlank { unknownCaller }
            val id = c.getLong("id")
            Notifications.show(
                appContext, AppConfig.NOTIFICATION_ID_CALL_BASE + id.toInt(),
                appContext.getString(R.string.notify_new_call, who), c.optString("summary")
            )
            lastShownCallId = maxOf(lastShownCallId, id)
        }

        // Cursors are saved only after the items were shown. When the server cut the list (it sends a
        // limited number per answer) the cursor stops at the last item shown, so the rest arrives next time.
        prefs.lastMessageId = if (lastShownMessageId >= 0) lastShownMessageId else json.getLong("max_message_id")
        prefs.lastCallId = if (lastShownCallId >= 0) lastShownCallId else json.getLong("max_call_id")
        Outcome(messages.length() + calls.length())
    }

    /** Releases Tor unless a screen or the service is using it, or a poll is running right now. */
    suspend fun releaseTorIfUnused(app: App) {
        if (!AppConfig.RELEASE_TOR_AFTER_POLL) return
        if (!lock.tryLock()) return
        try {
            if (app.startedActivities.get() == 0 && !app.serviceActive.get()) app.tor.release()
        } finally {
            lock.unlock()
        }
    }
}
