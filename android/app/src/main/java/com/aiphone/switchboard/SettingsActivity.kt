package com.aiphone.switchboard

import android.Manifest
import android.app.ActivityManager
import android.content.ActivityNotFoundException
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.PowerManager
import android.provider.Settings
import android.text.format.DateFormat
import android.view.View
import android.widget.RadioGroup
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import com.google.android.material.button.MaterialButton
import com.google.android.material.button.MaterialButtonToggleGroup
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import com.google.android.material.materialswitch.MaterialSwitch
import com.google.android.material.timepicker.MaterialTimePicker
import com.google.android.material.timepicker.TimeFormat
import java.util.Calendar

/** Notification settings: on/off, how often to check, schedule, battery help, About and Unpair. */
class SettingsActivity : AppCompatActivity() {

    private lateinit var prefs: NotifyPrefs
    private lateinit var store: PairingStore

    private lateinit var switchNotify: MaterialSwitch
    private lateinit var cardMode: View
    private lateinit var cardInterval: View
    private lateinit var radioGroupMode: RadioGroup
    private lateinit var intervalGroup: MaterialButtonToggleGroup
    private lateinit var switchSchedule: MaterialSwitch
    private lateinit var scheduleContainer: View
    private lateinit var btnDayStart: MaterialButton
    private lateinit var btnDayEnd: MaterialButton
    private lateinit var btnDayMode: MaterialButton
    private lateinit var btnNightMode: MaterialButton

    /** Interval button id -> minutes, built from AppConfig. */
    private val intervalButtonIds = mutableMapOf<Int, Int>()

    /** True while the screen is being filled from the saved settings, so listeners stay quiet. */
    private var rendering = false

    private val notificationPermission =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
            if (granted) {
                enableNotifications()
            } else {
                render()
                Toast.makeText(this, R.string.notify_permission_denied, Toast.LENGTH_LONG).show()
            }
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_settings)
        findViewById<View>(R.id.root).applySystemBarInsets()
        prefs = NotifyPrefs(applicationContext)
        store = PairingStore(applicationContext)

        switchNotify = findViewById(R.id.switch_notify)
        cardMode = findViewById(R.id.card_mode)
        cardInterval = findViewById(R.id.card_interval)
        radioGroupMode = findViewById(R.id.radio_group_mode)
        intervalGroup = findViewById(R.id.interval_group)
        switchSchedule = findViewById(R.id.switch_schedule)
        scheduleContainer = findViewById(R.id.schedule_container)
        btnDayStart = findViewById(R.id.btn_day_start)
        btnDayEnd = findViewById(R.id.btn_day_end)
        btnDayMode = findViewById(R.id.btn_day_mode)
        btnNightMode = findViewById(R.id.btn_night_mode)

        buildIntervalButtons()
        wireListeners()
        render()
    }

    /** One toggle button per interval listed in AppConfig. */
    private fun buildIntervalButtons() {
        for (minutes in AppConfig.BALANCED_INTERVAL_CHOICES_MINUTES) {
            val button = MaterialButton(
                this, null, com.google.android.material.R.attr.materialButtonOutlinedStyle
            ).apply {
                id = View.generateViewId()
                text = getString(R.string.interval_minutes, minutes)
            }
            intervalButtonIds[button.id] = minutes
            intervalGroup.addView(button)
        }
    }

    private fun wireListeners() {
        findViewById<View>(R.id.btn_back).setOnClickListener { finish() }

        switchNotify.setOnCheckedChangeListener { _, checked ->
            if (rendering) return@setOnCheckedChangeListener
            if (checked) requestEnableNotifications() else disableNotifications()
        }

        radioGroupMode.setOnCheckedChangeListener { _, checkedId ->
            if (rendering) return@setOnCheckedChangeListener
            prefs.mode = when (checkedId) {
                R.id.radio_balanced -> PollMode.BALANCED
                R.id.radio_instant -> PollMode.INSTANT
                else -> PollMode.SAVER
            }
            settingsChanged()
        }

        intervalGroup.addOnButtonCheckedListener { _, checkedId, isChecked ->
            if (rendering || !isChecked) return@addOnButtonCheckedListener
            intervalButtonIds[checkedId]?.let { prefs.balancedIntervalMinutes = it }
            settingsChanged()
        }

        switchSchedule.setOnCheckedChangeListener { _, checked ->
            if (rendering) return@setOnCheckedChangeListener
            prefs.scheduleEnabled = checked
            settingsChanged()
        }

        btnDayStart.setOnClickListener {
            pickTime(prefs.dayStartMinute) { prefs.dayStartMinute = it; settingsChanged() }
        }
        btnDayEnd.setOnClickListener {
            pickTime(prefs.dayEndMinute) { prefs.dayEndMinute = it; settingsChanged() }
        }
        btnDayMode.setOnClickListener {
            pickMode(prefs.dayMode) { prefs.dayMode = it; settingsChanged() }
        }
        btnNightMode.setOnClickListener {
            pickMode(prefs.nightMode) { prefs.nightMode = it; settingsChanged() }
        }

        findViewById<View>(R.id.btn_battery).setOnClickListener { requestBackgroundAllowance() }
        findViewById<View>(R.id.btn_about).setOnClickListener {
            startActivity(Intent(this, AboutActivity::class.java))
        }
        findViewById<View>(R.id.btn_unpair).setOnClickListener { confirmUnpair() }
    }

    /** Fills every control from the saved settings. */
    private fun render() {
        rendering = true
        switchNotify.isChecked = prefs.enabled
        switchSchedule.isChecked = prefs.scheduleEnabled

        cardMode.visibility = if (prefs.scheduleEnabled) View.GONE else View.VISIBLE
        scheduleContainer.visibility = if (prefs.scheduleEnabled) View.VISIBLE else View.GONE
        cardInterval.visibility = if (prefs.balancedIsConfigured()) View.VISIBLE else View.GONE

        radioGroupMode.check(
            when (prefs.mode) {
                PollMode.BALANCED -> R.id.radio_balanced
                PollMode.INSTANT -> R.id.radio_instant
                else -> R.id.radio_saver
            }
        )
        intervalButtonIds.entries.firstOrNull { it.value == prefs.balancedIntervalMinutes }
            ?.let { intervalGroup.check(it.key) }

        btnDayStart.text = formatMinute(prefs.dayStartMinute)
        btnDayEnd.text = formatMinute(prefs.dayEndMinute)
        btnDayMode.text = getString(prefs.dayMode.labelRes)
        btnNightMode.text = getString(prefs.nightMode.labelRes)
        rendering = false
    }

    /** Applies a changed setting to the background work and refreshes the screen. */
    private fun settingsChanged() {
        PollScheduler.apply(this, restartService = true)
        render()
    }

    // ---- notifications on/off ----------------------------------------------------------------

    private fun requestEnableNotifications() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU && !Notifications.hasPermission(this)) {
            notificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
        } else {
            enableNotifications()
        }
    }

    private fun enableNotifications() {
        prefs.resetCursors()
        prefs.enabled = true
        PollScheduler.apply(this, restartService = true)
        PollScheduler.pollOnceSoon(this)
        render()
    }

    private fun disableNotifications() {
        prefs.enabled = false
        PollScheduler.cancelAll(this)
        render()
    }

    // ---- pickers -----------------------------------------------------------------------------

    private fun pickTime(currentMinute: Int, onPicked: (Int) -> Unit) {
        val picker = MaterialTimePicker.Builder()
            .setTimeFormat(if (DateFormat.is24HourFormat(this)) TimeFormat.CLOCK_24H else TimeFormat.CLOCK_12H)
            .setHour(currentMinute / AppConfig.MINUTES_PER_HOUR)
            .setMinute(currentMinute % AppConfig.MINUTES_PER_HOUR)
            .setTitleText(R.string.settings_pick_time)
            .build()
        picker.addOnPositiveButtonClickListener {
            onPicked(picker.hour * AppConfig.MINUTES_PER_HOUR + picker.minute)
        }
        picker.show(supportFragmentManager, TAG_TIME_PICKER)
    }

    /** Schedule slots may use every mode, including Off. */
    private fun pickMode(current: PollMode, onPicked: (PollMode) -> Unit) {
        val modes = PollMode.values()
        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.settings_choose_mode)
            .setSingleChoiceItems(
                modes.map { getString(it.labelRes) }.toTypedArray(), modes.indexOf(current)
            ) { dialog, which ->
                onPicked(modes[which])
                dialog.dismiss()
            }
            .setNegativeButton(android.R.string.cancel, null)
            .show()
    }

    private fun formatMinute(minuteOfDay: Int): String {
        val cal = Calendar.getInstance().apply {
            set(Calendar.HOUR_OF_DAY, minuteOfDay / AppConfig.MINUTES_PER_HOUR)
            set(Calendar.MINUTE, minuteOfDay % AppConfig.MINUTES_PER_HOUR)
        }
        return DateFormat.getTimeFormat(this).format(cal.time)
    }

    // ---- battery and unpair ------------------------------------------------------------------

    private fun requestBackgroundAllowance() {
        val power = getSystemService(PowerManager::class.java)
        if (power.isIgnoringBatteryOptimizations(packageName)) {
            Toast.makeText(this, R.string.settings_battery_already, Toast.LENGTH_SHORT).show()
            return
        }
        val direct = Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS)
            .setData(Uri.parse("package:$packageName"))
        try {
            startActivity(direct)
        } catch (_: ActivityNotFoundException) {
            try {
                startActivity(Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS))
            } catch (_: ActivityNotFoundException) {
                // This device offers no such screen: nothing more to open.
            }
        }
    }

    private fun confirmUnpair() {
        MaterialAlertDialogBuilder(this)
            .setMessage(R.string.unpair_confirm)
            .setPositiveButton(android.R.string.ok) { _, _ -> unpairAndExit() }
            .setNegativeButton(android.R.string.cancel, null)
            .show()
    }

    /**
     * Forgets the pairing and closes the app completely. Everything is written synchronously, the
     * background jobs are cancelled, every screen is closed (this one and the main one below it) and
     * only then the process stops (see App.exitCompletely). Killing it while a screen is still open
     * would make Android restart that screen, which would reconnect by itself.
     */
    private fun unpairAndExit() {
        prefs.disableAndResetNow()
        PollScheduler.cancelAllAndWait(this)
        store.clear()
        val app = application as App
        app.tor.stop()
        app.exitCompletely()
        getSystemService(ActivityManager::class.java).appTasks.forEach { it.finishAndRemoveTask() }
        finishAffinity()
    }

    private companion object {
        const val TAG_TIME_PICKER = "time_picker"
    }
}
