package com.aiphone.switchboard

/** Every tunable constant of the app lives here, so no magic numbers or URLs are scattered around. */
object AppConfig {

    /** Tag used for every log line of the app (adb logcat -s AISwitchboard). */
    const val LOG_TAG = "AISwitchboard"

    // ---- switchboard notification endpoint ----------------------------------------------------
    /** Must match 'tor_notify_port' in the switchboard daemon. */
    const val NOTIFY_PORT = 8502
    const val NOTIFY_PATH = "/api/events"

    /** false keeps Tor bound after each check in power-saving mode (faster, but uses more battery). */
    const val RELEASE_TOR_AFTER_POLL = true

    // ---- check frequency ----------------------------------------------------------------------
    /** Android's minimum period for background work (power-saving mode). */
    const val SAVER_INTERVAL_MINUTES = 15L
    /** Intervals offered for the balanced mode, in minutes. */
    val BALANCED_INTERVAL_CHOICES_MINUTES: List<Int> = listOf(2, 5, 10)
    const val BALANCED_INTERVAL_DEFAULT_MINUTES = 5

    /** Instant mode: how long one request may be held open by the switchboard. */
    const val LONG_POLL_WAIT_SECONDS = 25
    /** If a long request returns faster than this with nothing new, the server has no long-poll support. */
    const val LONG_POLL_MIN_ELAPSED_SECONDS = 5L
    /** Pause applied in that case, so an older switchboard is never hammered. */
    const val LONG_POLL_MIN_GAP_SECONDS = 15L
    /** Extra socket time on top of the long-poll wait (Tor can be slow). */
    const val HTTP_TIMEOUT_MARGIN_SECONDS = 90
    const val HTTP_TIMEOUT_DEFAULT_MS = 120_000

    // ---- exit after unpairing -------------------------------------------------------------------
    /** If the screens have not finished closing after this long, the process is stopped anyway. */
    const val EXIT_FALLBACK_DELAY_MS = 2_000L
    /** Maximum wait for Android to confirm that the background jobs were cancelled. */
    const val WORK_CANCEL_TIMEOUT_SECONDS = 3L

    // ---- errors and idling ----------------------------------------------------------------------
    const val FAILURE_BACKOFF_BASE_SECONDS = 30L
    const val FAILURE_BACKOFF_MAX_SECONDS = 300L
    /** How often the background service re-checks the schedule while it has nothing to poll. */
    const val IDLE_TICK_SECONDS = 60L
    const val WORKER_MAX_ATTEMPTS = 2

    // ---- schedule defaults (minutes after midnight) ---------------------------------------------
    const val DEFAULT_DAY_START_MINUTE = 8 * 60
    const val DEFAULT_DAY_END_MINUTE = 22 * 60
    const val MINUTES_PER_HOUR = 60
    const val MINUTES_PER_DAY = 24 * 60

    // ---- notification ids ---------------------------------------------------------------------
    const val NOTIFICATION_ID_MESSAGE_BASE = 1_000_000
    const val NOTIFICATION_ID_CALL_BASE = 2_000_000
    const val NOTIFICATION_ID_SERVICE = 3_000_000

    // ---- links shown in the About screen ------------------------------------------------------
    const val REPO_URL = "https://github.com/antor44/AI-Bluetooth-Phone-Assistant"
    const val GPL_URL = "https://www.gnu.org/licenses/gpl-3.0.html"
    const val TOR_ANDROID_URL = "https://github.com/guardianproject/tor-android"
    const val NOTO_EMOJI_URL = "https://github.com/googlefonts/noto-emoji"
    const val MLKIT_TERMS_URL = "https://developers.google.com/ml-kit/terms"
}
