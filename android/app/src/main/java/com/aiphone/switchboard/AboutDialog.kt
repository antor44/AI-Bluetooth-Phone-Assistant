package com.aiphone.switchboard

import android.content.ActivityNotFoundException
import android.content.Intent
import android.graphics.Typeface
import android.net.Uri
import android.widget.ScrollView
import android.widget.TextView
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity

/** "About" screen: app version, GPL v3 notice, link to the source code and third-party licenses. */
object AboutDialog {

    private const val REPO_URL = "https://github.com/antor44/AI-Bluetooth-Phone-Assistant"
    private const val GPL_URL = "https://www.gnu.org/licenses/gpl-3.0.html"

    /** One line of the licenses list. assetName is null when there is no license text to bundle. */
    private data class Entry(val title: String, val header: String, val assetName: String?)

    private val entries = listOf(
        Entry(
            "AI Switchboard (this app) - GNU GPL v3",
            "Copyright (C) 2026 Antonio R.\nSource code: $REPO_URL\nLicense: $GPL_URL\n\n",
            "GPL-3.0.txt"
        ),
        Entry(
            "Tor (tor-android, jtorctl) - BSD 3-Clause",
            "Embedded Tor by The Tor Project and the Guardian Project.\n" +
                "https://github.com/guardianproject/tor-android\n" +
                "Copyright (c) The Tor Project, Inc. and the Guardian Project contributors.\n" +
                "The text below is the BSD 3-Clause license these components are distributed under.\n\n",
            "BSD-3-Clause.txt"
        ),
        Entry(
            "AndroidX, Kotlin and Kotlinx Coroutines - Apache 2.0",
            "Copyright The Android Open Source Project, JetBrains s.r.o. and contributors.\n\n",
            "Apache-2.0.txt"
        ),
        Entry(
            "Noto Emoji artwork (app icon) - Apache 2.0",
            "Copyright Google Inc. The app icon is based on a Noto Emoji image.\n" +
                "https://github.com/googlefonts/noto-emoji\n\n",
            "Apache-2.0.txt"
        ),
        Entry(
            "Google Play services code scanner - Google terms",
            "Used only to read the pairing QR code. It is provided by Google Play services at run time " +
                "and is not part of this app's source code. Terms: https://developers.google.com/ml-kit/terms\n",
            null
        )
    )

    fun show(activity: AppCompatActivity) {
        val info = activity.packageManager.getPackageInfo(activity.packageName, 0)
        @Suppress("DEPRECATION")
        val build = info.versionCode
        val text = buildString {
            append(activity.getString(R.string.about_version, info.versionName ?: "?", build)).append("\n\n")
            append(activity.getString(R.string.about_privacy)).append("\n\n")
            append(activity.getString(R.string.about_gpl_notice))
        }
        AlertDialog.Builder(activity)
            .setTitle(R.string.app_name)
            .setView(scrollable(activity, text, monospace = false))
            .setPositiveButton(R.string.about_licenses) { _, _ -> showLicenseList(activity) }
            .setNeutralButton(R.string.about_source) { _, _ -> openUrl(activity, REPO_URL) }
            .setNegativeButton(R.string.about_close, null)
            .show()
    }

    private fun showLicenseList(activity: AppCompatActivity) {
        AlertDialog.Builder(activity)
            .setTitle(R.string.about_licenses)
            .setItems(entries.map { it.title }.toTypedArray()) { _, which -> showLicenseText(activity, entries[which]) }
            .setNegativeButton(R.string.about_close, null)
            .show()
    }

    private fun showLicenseText(activity: AppCompatActivity, entry: Entry) {
        val body = entry.assetName?.let { name ->
            runCatching {
                activity.assets.open("licenses/$name").bufferedReader().use { it.readText() }
            }.getOrDefault("")
        }.orEmpty()
        AlertDialog.Builder(activity)
            .setTitle(entry.title)
            .setView(scrollable(activity, entry.header + body, monospace = true))
            .setPositiveButton(R.string.about_close, null)
            .show()
    }

    private fun scrollable(activity: AppCompatActivity, text: String, monospace: Boolean): ScrollView {
        val pad = (20 * activity.resources.displayMetrics.density).toInt()
        val view = TextView(activity).apply {
            this.text = text
            setPadding(pad, pad, pad, pad)
            setTextIsSelectable(true)
            if (monospace) { typeface = Typeface.MONOSPACE; textSize = 11f }
        }
        return ScrollView(activity).apply { addView(view) }
    }

    private fun openUrl(activity: AppCompatActivity, url: String) {
        try {
            activity.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
        } catch (_: ActivityNotFoundException) {
            // No browser installed: nothing to open.
        }
    }
}
