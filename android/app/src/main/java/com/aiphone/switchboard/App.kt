package com.aiphone.switchboard

import android.app.Activity
import android.app.Application
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.Process
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicInteger

class App : Application() {
    /** One Tor instance for the whole process (re-binding TorService repeatedly is fragile). */
    val tor: TorManager by lazy { TorManager(applicationContext) }

    /** Number of started screens (any activity); background work only releases Tor when this is zero. */
    val startedActivities = AtomicInteger(0)

    /** Set when the user unpaired: the process stops as soon as the last screen is gone. */
    @Volatile private var exitRequested = false

    /** Number of screens that exist (created and not yet destroyed). */
    private val liveActivities = AtomicInteger(0)

    /** True while the foreground service exists. */
    val serviceRunning = AtomicBoolean(false)

    /** True while the service is actively polling (and therefore holds Tor open). */
    val serviceActive = AtomicBoolean(false)

    override fun onCreate() {
        super.onCreate()
        registerActivityLifecycleCallbacks(object : ActivityLifecycleCallbacks {
            override fun onActivityStarted(activity: Activity) { startedActivities.incrementAndGet() }
            override fun onActivityStopped(activity: Activity) { startedActivities.decrementAndGet() }
            override fun onActivityCreated(activity: Activity, savedInstanceState: Bundle?) {
                liveActivities.incrementAndGet()
            }
            override fun onActivityResumed(activity: Activity) {}
            override fun onActivityPaused(activity: Activity) {}
            override fun onActivitySaveInstanceState(activity: Activity, outState: Bundle) {}
            override fun onActivityDestroyed(activity: Activity) {
                if (liveActivities.decrementAndGet() <= 0 && exitRequested) stopProcess()
            }
        })
        Notifications.ensureChannels(this)
        // After an update or a force stop the periodic job may be gone: register it again.
        PollScheduler.ensureWorkerIfEnabled(this)
    }

    /**
     * Closes the app for good after unpairing. The process is only stopped once every screen has been
     * destroyed: killing it earlier makes Android restart the screen that was still open, which then
     * reconnects by itself.
     */
    fun exitCompletely() {
        exitRequested = true
        Handler(Looper.getMainLooper()).postDelayed({ stopProcess() }, AppConfig.EXIT_FALLBACK_DELAY_MS)
    }

    private fun stopProcess() {
        Process.killProcess(Process.myPid())   // also drops the key from Tor's memory
    }
}
