package com.aiphone.switchboard

import android.Manifest
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat

object Notifications {
    private const val EVENTS_CHANNEL_ID = "switchboard_events"
    private const val SERVICE_CHANNEL_ID = "switchboard_service"

    fun ensureChannels(context: Context) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val manager = context.getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(
            NotificationChannel(
                EVENTS_CHANNEL_ID, context.getString(R.string.notify_channel_name),
                NotificationManager.IMPORTANCE_DEFAULT
            ).apply { description = context.getString(R.string.notify_channel_desc) }
        )
        // Silent channel for the permanent notification of the background service.
        manager.createNotificationChannel(
            NotificationChannel(
                SERVICE_CHANNEL_ID, context.getString(R.string.service_channel_name),
                NotificationManager.IMPORTANCE_LOW
            ).apply { description = context.getString(R.string.service_channel_desc) }
        )
    }

    fun hasPermission(context: Context): Boolean =
        Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU ||
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) ==
            PackageManager.PERMISSION_GRANTED

    private fun openAppIntent(context: Context): PendingIntent = PendingIntent.getActivity(
        context, 0, Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
        PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
    )

    /** Shows one notification. The lock screen only shows a generic text (private content hidden). */
    fun show(context: Context, id: Int, title: String, text: String) {
        if (!hasPermission(context)) return
        val publicVersion = NotificationCompat.Builder(context, EVENTS_CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_stat_notify)
            .setContentTitle(context.getString(R.string.notify_private_title))
            .build()
        val notification = NotificationCompat.Builder(context, EVENTS_CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_stat_notify)
            .setContentTitle(title)
            .setContentText(text)
            .setStyle(NotificationCompat.BigTextStyle().bigText(text))
            .setContentIntent(openAppIntent(context))
            .setAutoCancel(true)
            .setOnlyAlertOnce(true)
            .setVisibility(NotificationCompat.VISIBILITY_PRIVATE)
            .setPublicVersion(publicVersion)
            .build()
        NotificationManagerCompat.from(context).notify(id, notification)
    }

    /** The permanent, silent notification Android requires while the background service runs. */
    fun buildServiceNotification(context: Context, text: String): Notification =
        NotificationCompat.Builder(context, SERVICE_CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_stat_notify)
            .setContentTitle(context.getString(R.string.service_title))
            .setContentText(text)
            .setContentIntent(openAppIntent(context))
            .setOngoing(true)
            .setSilent(true)
            .setCategory(NotificationCompat.CATEGORY_SERVICE)
            .setVisibility(NotificationCompat.VISIBILITY_SECRET)
            .build()

    fun updateServiceNotification(context: Context, text: String) {
        if (!hasPermission(context)) return
        NotificationManagerCompat.from(context)
            .notify(AppConfig.NOTIFICATION_ID_SERVICE, buildServiceNotification(context, text))
    }
}
