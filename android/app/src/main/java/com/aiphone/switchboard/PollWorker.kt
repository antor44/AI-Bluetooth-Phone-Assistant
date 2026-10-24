package com.aiphone.switchboard

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.withContext

/**
 * Periodic check done by Android's job scheduler (about every 15 minutes). It is the whole
 * mechanism in power-saving mode, and a safety net in the other modes: if the foreground service is
 * running it does nothing, otherwise it polls once so alerts still arrive.
 */
class PollWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result {
        val app = applicationContext as App
        val prefs = NotifyPrefs(applicationContext)
        if (!prefs.enabled || PairingStore(applicationContext).load() == null) return Result.success()

        val mode = prefs.effectiveMode()
        if (mode == PollMode.OFF) return Result.success()
        if (mode.usesService && app.serviceActive.get()) return Result.success()

        return try {
            PollEngine.pollOnce(applicationContext)
            Result.success()
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            if (runAttemptCount < AppConfig.WORKER_MAX_ATTEMPTS) Result.retry() else Result.success()
        } finally {
            withContext(NonCancellable) { PollEngine.releaseTorIfUnused(app) }
        }
    }
}
