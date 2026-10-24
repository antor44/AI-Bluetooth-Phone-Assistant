package com.aiphone.switchboard

import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.os.SystemClock
import android.util.Log
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.util.concurrent.TimeUnit
import kotlin.math.min

/**
 * Foreground service for the "balanced" and "instant" modes. It keeps Tor open and checks the
 * switchboard every few minutes (balanced) or keeps one request open all the time (instant).
 * When the schedule says another mode applies (for example power saving at night) it just waits
 * and lets the periodic job do the checking.
 */
class PollService : Service() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    private var loopJob: Job? = null
    private var lastNotificationText: String? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        (application as App).serviceRunning.set(true)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        // Android requires startForeground() soon after the service starts, whatever happens next.
        // The text already names the mode in force, so no placeholder is ever shown.
        val prefs = NotifyPrefs(this)
        val started = runCatching { startInForeground(stateText(prefs.effectiveMode(), prefs)) }.isSuccess
        if (!started || !prefs.enabled) {
            stopSelf()
            return START_NOT_STICKY
        }
        loopJob?.cancel()
        loopJob = scope.launch { runLoop() }
        return START_STICKY
    }

    override fun onDestroy() {
        val app = application as App
        app.serviceRunning.set(false)
        app.serviceActive.set(false)
        scope.cancel()
        // Let go of Tor if nothing else is using it (best effort, runs on its own scope).
        CoroutineScope(Dispatchers.Default).launch { PollEngine.releaseTorIfUnused(app) }
        super.onDestroy()
    }

    private fun startInForeground(text: String) {
        val type = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE
        } else {
            0
        }
        ServiceCompat.startForeground(
            this, AppConfig.NOTIFICATION_ID_SERVICE,
            Notifications.buildServiceNotification(this, text), type
        )
        lastNotificationText = text
    }

    private suspend fun runLoop() {
        val app = application as App
        var failures = 0
        while (true) {
            val prefs = NotifyPrefs(applicationContext)
            if (!prefs.enabled) {
                stopSelf()
                return
            }
            val mode = prefs.effectiveMode()
            showState(mode, prefs)

            if (!mode.usesService) {
                // Nothing to do now (power saving or off): let the periodic job work, release Tor.
                app.serviceActive.set(false)
                PollEngine.releaseTorIfUnused(app)
                delay(TimeUnit.SECONDS.toMillis(AppConfig.IDLE_TICK_SECONDS))
                continue
            }

            app.serviceActive.set(true)
            val startedAt = SystemClock.elapsedRealtime()
            try {
                val waitSeconds = if (mode == PollMode.INSTANT) AppConfig.LONG_POLL_WAIT_SECONDS else 0
                val outcome = PollEngine.pollOnce(applicationContext, waitSeconds)
                failures = 0
                if (mode == PollMode.BALANCED) {
                    delay(TimeUnit.MINUTES.toMillis(prefs.balancedIntervalMinutes.toLong()))
                } else {
                    val elapsedMs = SystemClock.elapsedRealtime() - startedAt
                    val tooFast = elapsedMs < TimeUnit.SECONDS.toMillis(AppConfig.LONG_POLL_MIN_ELAPSED_SECONDS)
                    if (outcome.itemCount == 0 && tooFast) {
                        delay(TimeUnit.SECONDS.toMillis(AppConfig.LONG_POLL_MIN_GAP_SECONDS))
                    }
                }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                Log.w(AppConfig.LOG_TAG, "Background check failed (attempt $failures)", e)
                failures++
                val backoff = AppConfig.FAILURE_BACKOFF_BASE_SECONDS * (1L shl min(failures - 1, 4))
                delay(TimeUnit.SECONDS.toMillis(min(backoff, AppConfig.FAILURE_BACKOFF_MAX_SECONDS)))
            }
        }
    }

    /** The permanent notification always names the mode that is in force right now. */
    private fun stateText(mode: PollMode, prefs: NotifyPrefs): String = when (mode) {
        PollMode.INSTANT -> getString(R.string.service_text_instant)
        PollMode.BALANCED -> getString(R.string.service_text_balanced, prefs.balancedIntervalMinutes)
        PollMode.SAVER -> getString(R.string.service_text_saver, AppConfig.SAVER_INTERVAL_MINUTES)
        PollMode.OFF -> getString(R.string.service_text_off)
    }

    /** Keeps the permanent notification text in line with what the service is doing. */
    private fun showState(mode: PollMode, prefs: NotifyPrefs) {
        val text = stateText(mode, prefs)
        if (text == lastNotificationText) return
        lastNotificationText = text
        Notifications.updateServiceNotification(this, text)
    }

    companion object {
        fun start(context: Context) {
            try {
                ContextCompat.startForegroundService(context, Intent(context, PollService::class.java))
            } catch (_: Exception) {
                // Android refuses to start it from the background; the periodic job still covers us.
            }
        }

        fun stop(context: Context) {
            context.stopService(Intent(context, PollService::class.java))
        }
    }
}
