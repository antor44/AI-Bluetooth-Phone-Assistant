package com.aiphone.switchboard

import android.content.Context
import androidx.annotation.StringRes
import java.util.Calendar

/** How the app looks for new switchboard activity. */
enum class PollMode(val storageKey: String, @StringRes val labelRes: Int) {
    /** No checks at all (only meaningful as a schedule slot, e.g. "off at night"). */
    OFF("off", R.string.mode_off),
    /** One check about every 15 minutes, done by Android's job scheduler. */
    SAVER("saver", R.string.mode_saver),
    /** A check every few minutes, done by a foreground service. */
    BALANCED("balanced", R.string.mode_balanced),
    /** One request is always open, so alerts arrive almost immediately. */
    INSTANT("instant", R.string.mode_instant);

    /** True for the modes that need the foreground service. */
    val usesService: Boolean get() = this == BALANCED || this == INSTANT

    companion object {
        fun fromKey(key: String?, fallback: PollMode): PollMode =
            values().firstOrNull { it.storageKey == key } ?: fallback
    }
}

/** Minutes after midnight for the current local time. */
fun currentMinuteOfDay(): Int {
    val now = Calendar.getInstance()
    return now.get(Calendar.HOUR_OF_DAY) * AppConfig.MINUTES_PER_HOUR + now.get(Calendar.MINUTE)
}

/** Local settings of the notification checks (no secrets: plain preferences are enough). */
class NotifyPrefs(context: Context) {
    private val prefs = context.getSharedPreferences(FILE_NAME, Context.MODE_PRIVATE)

    var enabled: Boolean
        get() = prefs.getBoolean(KEY_ENABLED, false)
        set(v) { prefs.edit().putBoolean(KEY_ENABLED, v).apply() }

    /** Mode used when no schedule is set. */
    var mode: PollMode
        get() = PollMode.fromKey(prefs.getString(KEY_MODE, null), PollMode.SAVER)
        set(v) { prefs.edit().putString(KEY_MODE, v.storageKey).apply() }

    var balancedIntervalMinutes: Int
        get() = prefs.getInt(KEY_BALANCED_MINUTES, AppConfig.BALANCED_INTERVAL_DEFAULT_MINUTES)
        set(v) { prefs.edit().putInt(KEY_BALANCED_MINUTES, v).apply() }

    var scheduleEnabled: Boolean
        get() = prefs.getBoolean(KEY_SCHEDULE_ENABLED, false)
        set(v) { prefs.edit().putBoolean(KEY_SCHEDULE_ENABLED, v).apply() }

    var dayStartMinute: Int
        get() = prefs.getInt(KEY_DAY_START, AppConfig.DEFAULT_DAY_START_MINUTE)
        set(v) { prefs.edit().putInt(KEY_DAY_START, v).apply() }

    var dayEndMinute: Int
        get() = prefs.getInt(KEY_DAY_END, AppConfig.DEFAULT_DAY_END_MINUTE)
        set(v) { prefs.edit().putInt(KEY_DAY_END, v).apply() }

    var dayMode: PollMode
        get() = PollMode.fromKey(prefs.getString(KEY_DAY_MODE, null), PollMode.BALANCED)
        set(v) { prefs.edit().putString(KEY_DAY_MODE, v.storageKey).apply() }

    var nightMode: PollMode
        get() = PollMode.fromKey(prefs.getString(KEY_NIGHT_MODE, null), PollMode.SAVER)
        set(v) { prefs.edit().putString(KEY_NIGHT_MODE, v.storageKey).apply() }

    /** -1 means "not initialised": the next poll only stores the server cursors. */
    var lastMessageId: Long
        get() = prefs.getLong(KEY_LAST_MESSAGE, -1L)
        set(v) { prefs.edit().putLong(KEY_LAST_MESSAGE, v).apply() }

    var lastCallId: Long
        get() = prefs.getLong(KEY_LAST_CALL, -1L)
        set(v) { prefs.edit().putLong(KEY_LAST_CALL, v).apply() }

    /** Turns notifications off and forgets the cursors, written synchronously (the process may die next). */
    fun disableAndResetNow() {
        prefs.edit().putBoolean(KEY_ENABLED, false).remove(KEY_LAST_MESSAGE).remove(KEY_LAST_CALL).commit()
    }

    fun resetCursors() {
        prefs.edit().remove(KEY_LAST_MESSAGE).remove(KEY_LAST_CALL).apply()
    }

    /** Day runs from dayStart (included) to dayEnd (excluded) and may cross midnight. Equal values = always day. */
    fun isDayTime(minuteOfDay: Int): Boolean {
        val start = dayStartMinute
        val end = dayEndMinute
        return when {
            start == end -> true
            start < end -> minuteOfDay in start until end
            else -> minuteOfDay >= start || minuteOfDay < end
        }
    }

    /** The mode that applies right now, taking the schedule into account. */
    fun effectiveMode(minuteOfDay: Int = currentMinuteOfDay()): PollMode = when {
        !scheduleEnabled -> mode
        isDayTime(minuteOfDay) -> dayMode
        else -> nightMode
    }

    /** True when the foreground service is needed at some point of the day. */
    fun anyServiceModeConfigured(): Boolean =
        if (scheduleEnabled) dayMode.usesService || nightMode.usesService else mode.usesService

    /** True when the balanced interval setting matters for the current configuration. */
    fun balancedIsConfigured(): Boolean =
        if (scheduleEnabled) dayMode == PollMode.BALANCED || nightMode == PollMode.BALANCED
        else mode == PollMode.BALANCED

    private companion object {
        const val FILE_NAME = "notify"
        const val KEY_ENABLED = "enabled"
        const val KEY_MODE = "mode"
        const val KEY_BALANCED_MINUTES = "balanced_minutes"
        const val KEY_SCHEDULE_ENABLED = "schedule_enabled"
        const val KEY_DAY_START = "day_start"
        const val KEY_DAY_END = "day_end"
        const val KEY_DAY_MODE = "day_mode"
        const val KEY_NIGHT_MODE = "night_mode"
        const val KEY_LAST_MESSAGE = "last_message_id"
        const val KEY_LAST_CALL = "last_call_id"
    }
}
