package com.aiphone.switchboard

import android.app.Application
import java.util.concurrent.atomic.AtomicInteger

class App : Application() {
    /** One Tor instance for the whole process (re-binding TorService repeatedly is fragile). */
    val tor: TorManager by lazy { TorManager(applicationContext) }

    /** Number of started activities; the background poll only releases Tor when this is zero. */
    val startedActivities = AtomicInteger(0)

    override fun onCreate() {
        super.onCreate()
        Notifications.ensureChannel(this)
    }
}
