package com.aiphone.switchboard

import android.annotation.SuppressLint
import android.app.ActivityManager
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.util.Log
import android.view.View
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.TextView
import androidx.activity.OnBackPressedCallback
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import androidx.webkit.ProxyConfig
import androidx.webkit.ProxyController
import androidx.webkit.WebViewFeature
import com.google.android.material.button.MaterialButton
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import com.google.android.material.progressindicator.LinearProgressIndicator
import com.google.android.material.textfield.TextInputEditText
import com.google.mlkit.vision.barcode.common.Barcode
import com.google.mlkit.vision.codescanner.GmsBarcodeScannerOptions
import com.google.mlkit.vision.codescanner.GmsBarcodeScanning
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import java.io.ByteArrayInputStream

class MainActivity : AppCompatActivity() {

    private lateinit var store: PairingStore

    private lateinit var pairingView: View
    private lateinit var mainView: View
    private lateinit var pairError: TextView
    private lateinit var statusText: TextView
    private lateinit var progress: LinearProgressIndicator
    private lateinit var retryButton: MaterialButton
    private lateinit var webView: WebView

    private var currentPairing: Pairing? = null
    private var connectJob: Job? = null

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        findViewById<View>(R.id.root).applySystemBarInsets()
        store = PairingStore(applicationContext)

        pairingView = findViewById(R.id.pairing_view)
        mainView = findViewById(R.id.main_view)
        pairError = findViewById(R.id.pair_error)
        statusText = findViewById(R.id.status_text)
        progress = findViewById(R.id.progress)
        retryButton = findViewById(R.id.btn_retry)
        webView = findViewById(R.id.web_view)

        webView.settings.apply {
            javaScriptEnabled = true      // Streamlit needs JS
            domStorageEnabled = true
            allowFileAccess = false
            allowContentAccess = false
        }

        findViewById<View>(R.id.btn_scan).setOnClickListener { scanQr() }
        findViewById<View>(R.id.btn_pair).setOnClickListener {
            val first = findViewById<TextInputEditText>(R.id.input_pairing).text.toString()
            val key = findViewById<TextInputEditText>(R.id.input_key).text.toString()
            handlePairingFields(first, key)
        }
        findViewById<View>(R.id.btn_pair_about).setOnClickListener { openAbout() }
        findViewById<View>(R.id.btn_refresh).setOnClickListener { refresh() }
        findViewById<View>(R.id.btn_settings).setOnClickListener {
            startActivity(Intent(this, SettingsActivity::class.java))
        }
        findViewById<View>(R.id.btn_close).setOnClickListener { confirmClose() }
        retryButton.setOnClickListener { currentPairing?.let { connect(it, fresh = true) } }

        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (mainView.visibility == View.VISIBLE && webView.canGoBack()) webView.goBack() else finish()
            }
        })

        val saved = store.load()
        if (saved == null) showPairingScreen() else showMainScreen(saved)
    }

    override fun onStart() {
        super.onStart()
        val app = application as App
        // A background poll may have released Tor while the app was away: reconnect the screen.
        val p = currentPairing
        if (p != null && app.tor.released) connect(p)
        // Opening the app also repairs the background checks if Android stopped them.
        PollScheduler.apply(this)
    }

    override fun onDestroy() {
        webView.destroy()
        super.onDestroy()
    }

    // ---- pairing screen ----------------------------------------------------------------------

    private fun showPairingScreen(error: String? = null) {
        currentPairing = null
        mainView.visibility = View.GONE
        pairingView.visibility = View.VISIBLE
        pairError.text = error.orEmpty()
    }

    private fun scanQr() {
        val options = GmsBarcodeScannerOptions.Builder()
            .setBarcodeFormats(Barcode.FORMAT_QR_CODE)
            .build()
        GmsBarcodeScanning.getClient(this, options).startScan()
            .addOnSuccessListener { barcode -> handlePairingText(barcode.rawValue.orEmpty()) }
            .addOnFailureListener { showPairingScreen(getString(R.string.scan_failed)) }
    }

    /** Pairing from two fields (onion address + access key) or from one full pairing text. */
    private fun handlePairingFields(first: String, key: String) {
        if (key.isBlank()) {
            handlePairingText(first)
            return
        }
        val p = Pairing.build(first, key)
        if (p == null) {
            showPairingScreen(getString(R.string.pair_invalid))
            return
        }
        store.save(p)
        showMainScreen(p)
    }

    private fun handlePairingText(text: String) {
        val p = Pairing.parse(text)
        if (p == null) {
            showPairingScreen(getString(R.string.pair_invalid))
            return
        }
        store.save(p)
        showMainScreen(p)
    }

    // ---- main screen -------------------------------------------------------------------------

    private fun showMainScreen(p: Pairing) {
        currentPairing = p
        pairingView.visibility = View.GONE
        mainView.visibility = View.VISIBLE
        webView.webViewClient = onionOnlyClient(p)
        connect(p)
    }

    /**
     * Refresh button. Only when the page is showing correctly does it simply reload the page.
     * In any other case (still connecting, stuck, or the last attempt ended in an error) it gives up
     * the current attempt and connects again from scratch, with a fresh Tor.
     */
    private fun refresh() {
        val p = currentPairing ?: return
        val tor = (application as App).tor
        val pageIsShowing = connectJob?.isActive != true &&
            webView.visibility == View.VISIBLE &&
            !tor.released &&
            retryButton.visibility != View.VISIBLE
        if (pageIsShowing) {
            statusText.text = getString(R.string.connected)
            webView.reload()
        } else {
            connect(p, fresh = true)
        }
    }

    /**
     * @param fresh false: do nothing if an attempt is already running (used when the screen comes
     * back). true: cancel the running attempt, let go of Tor and start again from zero (used by the
     * refresh and retry buttons, so they always do something).
     */
    private fun connect(p: Pairing, fresh: Boolean = false) {
        if (fresh) {
            connectJob?.cancel()
        } else if (connectJob?.isActive == true) {
            return
        }
        statusText.text = getString(R.string.connecting, 0)
        progress.visibility = View.VISIBLE
        progress.setProgressCompat(0, false)
        retryButton.visibility = View.GONE
        webView.visibility = View.GONE
        connectJob = lifecycleScope.launch {
            try {
                val tor = (application as App).tor
                if (fresh) tor.release()
                val (host, port) = tor.start(p) { pct ->
                    runOnUiThread {
                        statusText.text = getString(R.string.connecting, pct)
                        progress.setProgressCompat(pct, true)
                    }
                }
                loadThroughProxy(host, port, p)
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                Log.e(AppConfig.LOG_TAG, "Connection through Tor failed", e)
                showError(getString(R.string.error_generic, e.message ?: e.javaClass.simpleName))
            }
        }
    }

    /** Only the paired onion host may load; everything else is blocked (no leaks outside Tor). */
    private fun onionOnlyClient(p: Pairing) = object : WebViewClient() {
        private fun allowed(uri: Uri) = uri.host.equals(p.onion, ignoreCase = true)

        override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean =
            !allowed(request.url)

        override fun shouldInterceptRequest(
            view: WebView, request: WebResourceRequest
        ): WebResourceResponse? =
            if (allowed(request.url)) null
            else WebResourceResponse(
                "text/plain", "utf-8", 403, "Blocked", emptyMap(), ByteArrayInputStream(ByteArray(0))
            )

        override fun onReceivedError(
            view: WebView, request: WebResourceRequest, error: WebResourceError
        ) {
            if (request.isForMainFrame) {
                Log.w(AppConfig.LOG_TAG, "Page load failed: code ${error.errorCode}, ${error.description}")
                showError(getString(R.string.page_error))
            }
        }
    }

    private fun loadThroughProxy(host: String, port: Int, p: Pairing) {
        if (!WebViewFeature.isFeatureSupported(WebViewFeature.PROXY_OVERRIDE)) {
            showError(getString(R.string.webview_unsupported))
            return
        }
        // VERIFY: "socks5://" so that Chromium sends the .onion hostname to Tor (remote DNS).
        val cfg = ProxyConfig.Builder().addProxyRule("socks5://$host:$port").build()
        ProxyController.getInstance().setProxyOverride(cfg, ContextCompat.getMainExecutor(this)) {
            statusText.text = getString(R.string.connected)
            progress.visibility = View.GONE
            retryButton.visibility = View.GONE
            webView.visibility = View.VISIBLE
            webView.loadUrl(p.url)
        }
    }

    private fun showError(message: String) {
        statusText.text = message
        progress.visibility = View.GONE
        retryButton.visibility = View.VISIBLE
    }

    private fun openAbout() {
        startActivity(Intent(this, AboutActivity::class.java))
    }

    // ---- close the app -----------------------------------------------------------------------

    private fun confirmClose() {
        MaterialAlertDialogBuilder(this)
            .setMessage(R.string.close_confirm)
            .setPositiveButton(android.R.string.ok) { _, _ -> closeApp() }
            .setNegativeButton(android.R.string.cancel, null)
            .show()
    }

    /**
     * Stops everything (background checks, permanent notification, Tor) and closes the app, but keeps
     * the pairing and every setting: when the app is opened again it starts the checks as configured.
     * Same closing sequence as unpairing (see SettingsActivity.unpairAndExit), minus the forgetting.
     */
    private fun closeApp() {
        PollScheduler.cancelAllAndWait(this)
        val app = application as App
        app.tor.stop()
        app.exitCompletely()
        getSystemService(ActivityManager::class.java).appTasks.forEach { it.finishAndRemoveTask() }
        finishAffinity()
    }
}
