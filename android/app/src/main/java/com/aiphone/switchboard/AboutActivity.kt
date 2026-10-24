package com.aiphone.switchboard

import android.content.ActivityNotFoundException
import android.content.Intent
import android.graphics.Typeface
import android.net.Uri
import android.os.Bundle
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.pm.PackageInfoCompat
import com.google.android.material.button.MaterialButton

/**
 * About screen: version, GPL v3 notice, source code link and third-party licenses.
 * It is a normal screen (not a dialog) and everything sits inside one scroll area, so no button or
 * link can ever end up hidden behind the system navigation bar.
 */
class AboutActivity : AppCompatActivity() {

    /** One entry of the licenses list. assetName is null when there is no license text to bundle. */
    private data class Entry(val title: String, val header: String, val assetName: String?)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_about)
        findViewById<View>(R.id.root).applySystemBarInsets()

        val info = packageManager.getPackageInfo(packageName, 0)
        findViewById<TextView>(R.id.about_version).text = getString(
            R.string.about_version, info.versionName ?: "?", PackageInfoCompat.getLongVersionCode(info)
        )
        findViewById<View>(R.id.btn_back).setOnClickListener { finish() }
        findViewById<View>(R.id.btn_source).setOnClickListener { openUrl(AppConfig.REPO_URL) }

        val container = findViewById<LinearLayout>(R.id.licenses_container)
        buildEntries().forEach { addLicenseEntry(container, it) }
    }

    private fun buildEntries() = listOf(
        Entry(
            getString(R.string.license_app_title),
            getString(R.string.license_app_header, AppConfig.REPO_URL, AppConfig.GPL_URL),
            "GPL-3.0.txt"
        ),
        Entry(
            getString(R.string.license_tor_title),
            getString(R.string.license_tor_header, AppConfig.TOR_ANDROID_URL),
            "BSD-3-Clause.txt"
        ),
        Entry(
            getString(R.string.license_androidx_title),
            getString(R.string.license_androidx_header),
            "Apache-2.0.txt"
        ),
        Entry(
            getString(R.string.license_noto_title),
            getString(R.string.license_noto_header, AppConfig.NOTO_EMOJI_URL),
            "Apache-2.0.txt"
        ),
        Entry(
            getString(R.string.license_scanner_title),
            getString(R.string.license_scanner_header, AppConfig.MLKIT_TERMS_URL),
            null
        )
    )

    /** A button that opens and closes the license text below it; the text is read only when first opened. */
    private fun addLicenseEntry(container: LinearLayout, entry: Entry) {
        val body = TextView(this).apply {
            visibility = View.GONE
            typeface = Typeface.MONOSPACE
            setTextSize(TypedValue.COMPLEX_UNIT_PX, resources.getDimension(R.dimen.text_license))
            setTextIsSelectable(true)
            setPadding(0, resources.getDimensionPixelSize(R.dimen.spacing_small), 0, 0)
        }
        val button = MaterialButton(
            this, null, com.google.android.material.R.attr.materialButtonOutlinedStyle
        ).apply {
            text = entry.title
            gravity = Gravity.START or Gravity.CENTER_VERTICAL
            layoutParams = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT
            ).apply { topMargin = resources.getDimensionPixelSize(R.dimen.spacing_small) }
            setOnClickListener {
                if (body.visibility == View.VISIBLE) {
                    body.visibility = View.GONE
                } else {
                    if (body.text.isNullOrEmpty()) body.text = entry.header + readAsset(entry.assetName)
                    body.visibility = View.VISIBLE
                }
            }
        }
        container.addView(button)
        container.addView(body)
    }

    private fun readAsset(name: String?): String {
        if (name == null) return ""
        return runCatching {
            assets.open("$ASSET_DIR/$name").bufferedReader().use { it.readText() }
        }.getOrDefault("")
    }

    private fun openUrl(url: String) {
        try {
            startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
        } catch (_: ActivityNotFoundException) {
            // No browser installed: nothing to open.
        }
    }

    private companion object {
        const val ASSET_DIR = "licenses"
    }
}
