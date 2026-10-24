package com.aiphone.switchboard

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/** Restores the background checks after the phone restarts or the app is updated. */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        when (intent.action) {
            Intent.ACTION_BOOT_COMPLETED, Intent.ACTION_MY_PACKAGE_REPLACED -> PollScheduler.apply(context)
        }
    }
}
