package com.aiphone.switchboard

import android.content.Context
import androidx.work.Constraints
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import java.util.concurrent.TimeUnit

/** Starts and stops the background pieces so that they match the saved settings. */
object PollScheduler {
    private const val WORK_NAME = "switchboard_poll"

    private fun constraints() = Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build()

    /** Registers the periodic job (no effect if it already exists). */
    fun ensureWorker(context: Context) {
        WorkManager.getInstance(context).enqueueUniquePeriodicWork(
            WORK_NAME, ExistingPeriodicWorkPolicy.KEEP,
            PeriodicWorkRequestBuilder<PollWorker>(AppConfig.SAVER_INTERVAL_MINUTES, TimeUnit.MINUTES)
                .setConstraints(constraints()).build()
        )
    }

    fun ensureWorkerIfEnabled(context: Context) {
        if (NotifyPrefs(context).enabled) ensureWorker(context)
    }

    /** One immediate check; the first one only stores the server cursors, so old items never notify. */
    fun pollOnceSoon(context: Context) {
        WorkManager.getInstance(context)
            .enqueue(OneTimeWorkRequestBuilder<PollWorker>().setConstraints(constraints()).build())
    }

    /**
     * Makes the running pieces match the settings.
     * @param restartService true after a settings change, so the service re-reads them at once.
     */
    fun apply(context: Context, restartService: Boolean = false) {
        val appContext = context.applicationContext
        val prefs = NotifyPrefs(appContext)
        val paired = runCatching { PairingStore(appContext).load() != null }.getOrDefault(false)
        if (!prefs.enabled || !paired) {
            cancelAll(appContext)
            return
        }
        ensureWorker(appContext)
        if (prefs.anyServiceModeConfigured()) {
            val app = appContext as App
            if (restartService || !app.serviceRunning.get()) PollService.start(appContext)
        } else {
            PollService.stop(appContext)
        }
    }

    /** Like cancelAll, but waits (briefly) until Android confirms the jobs are gone; used before exiting. */
    fun cancelAllAndWait(context: Context) {
        val appContext = context.applicationContext
        val operation = WorkManager.getInstance(appContext).cancelAllWork()
        runCatching { operation.result.get(AppConfig.WORK_CANCEL_TIMEOUT_SECONDS, TimeUnit.SECONDS) }
        PollService.stop(appContext)
    }

    fun cancelAll(context: Context) {
        val appContext = context.applicationContext
        WorkManager.getInstance(appContext).cancelUniqueWork(WORK_NAME)
        PollService.stop(appContext)
    }
}
