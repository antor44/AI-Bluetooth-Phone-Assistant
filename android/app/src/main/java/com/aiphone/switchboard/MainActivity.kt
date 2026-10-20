package com.aiphone.switchboard

import android.annotation.SuppressLint
import android.app.AlertDialog
import android.net.Uri
import android.Manifest
import android.os.Build
import android.os.Bundle
import android.os.Process
import android.text.InputType
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.ScrollView
import android.widget.TextView
import androidx.activity.OnBackPressedCallback
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.widget.SwitchCompat
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.lifecycle.lifecycleScope
import androidx.webkit.ProxyConfig
import androidx.webkit.ProxyController
import androidx.webkit.WebViewFeature
import com.google.mlkit.vision.barcode.common.Barcode
import com.google.mlkit.vision.codescanner.GmsBarcodeScannerOptions
import com.google.mlkit.vision.codescanner.GmsBarcodeScanning
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch
import java.io.ByteArrayInputStream

class MainActivity : AppCompatActivity() {

    private lateinit var store: PairingStore
    private lateinit var root: FrameLayout

    private var webView: WebView? = null
    private var statusText: TextView? = null
    private var progressBar: ProgressBar? = null
    private var retryButton: Button? = null
    private lateinit var notifyPrefs: NotifyPrefs
    private var notifySwitch: SwitchCompat? = null
    private var currentPairing: Pairing? = null

    private val notificationPermission =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
            if (granted) enableNotifications() else {
                notifySwitch?.isChecked = false
                android.widget.Toast.makeText(this, R.string.notify_permission_denied, android.widget.Toast.LENGTH_LONG).show()
            }
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        store = PairingStore(applicationContext)
        notifyPrefs = NotifyPrefs(applicationContext)

        root = FrameLayout(this)
        setContentView(root)
        ViewCompat.setOnApplyWindowInsetsListener(root) { v, insets ->
            val bars = insets.getInsets(
                WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.ime()
            )
            v.setPadding(bars.left, bars.top, bars.right, bars.bottom)
            insets
        }

        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                val wv = webView
                if (wv != null && wv.canGoBack()) wv.goBack() else finish()
            }
        })

        val saved = store.load()
        if (saved == null) showPairingScreen() else connect(saved)
    }

    override fun onStart() {
        super.onStart()
        (application as App).startedActivities.incrementAndGet()
        // A background poll may have released Tor while the app was away: reconnect the screen.
        val p = currentPairing
        if (p != null && (application as App).tor.released) connect(p)
    }

    override fun onStop() {
        (application as App).startedActivities.decrementAndGet()
        super.onStop()
    }

    override fun onDestroy() {
        webView?.destroy()
        webView = null
        super.onDestroy()
    }

    // ---- pairing screen ----------------------------------------------------------------------

    private fun showPairingScreen(error: String? = null) {
        webView = null; statusText = null; progressBar = null; retryButton = null
        root.removeAllViews()

        val pad = dp(24)
        val col = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(pad, pad, pad, pad)
        }
        col.addView(TextView(this).apply {
            setText(R.string.pair_title)
            textSize = 22f
        })
        col.addView(TextView(this).apply {
            setText(R.string.pair_hint)
            setPadding(0, dp(12), 0, dp(16))
        })
        col.addView(Button(this).apply {
            setText(R.string.pair_scan)
            setOnClickListener { scanQr() }
        })
        val input = EditText(this).apply {
            setHint(R.string.pair_paste_hint)
            minLines = 3
            gravity = Gravity.TOP
            inputType = InputType.TYPE_CLASS_TEXT or
                InputType.TYPE_TEXT_FLAG_MULTI_LINE or
                InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS
        }
        col.addView(input)
        // The switchboard GUI shows the access key on its own, so it has its own field.
        val keyInput = EditText(this).apply {
            setHint(R.string.pair_key_hint)
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS
        }
        col.addView(keyInput)
        col.addView(TextView(this).apply {
            setTextColor(0xFFB00020.toInt())
            text = error.orEmpty()
        })
        col.addView(Button(this).apply {
            setText(R.string.pair_save)
            setOnClickListener { handlePairingFields(input.text.toString(), keyInput.text.toString()) }
        })
        col.addView(Button(this).apply {
            setText(R.string.about_button)
            setOnClickListener { AboutDialog.show(this@MainActivity) }
        })
        root.addView(ScrollView(this).apply { addView(col) })
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
        connect(p)
    }

    private fun handlePairingText(text: String) {
        val p = Pairing.parse(text)
        if (p == null) {
            showPairingScreen(getString(R.string.pair_invalid))
            return
        }
        store.save(p)
        connect(p)
    }

    // ---- main screen -------------------------------------------------------------------------

    private fun connect(p: Pairing) {
        currentPairing = p
        buildMainScreen(p)
        lifecycleScope.launch {
            try {
                val (host, port) = (application as App).tor.start(p) { pct ->
                    runOnUiThread {
                        statusText?.text = getString(R.string.connecting, pct)
                        progressBar?.progress = pct
                    }
                }
                loadThroughProxy(host, port, p)
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                showError(getString(R.string.error_generic, e.message ?: e.javaClass.simpleName))
            }
        }
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun buildMainScreen(p: Pairing) {
        root.removeAllViews()

        val col = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }

        val bar = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(12), dp(4), dp(12), dp(4))
        }
        val status = TextView(this).apply {
            layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
            text = getString(R.string.connecting, 0)
        }
        val retry = Button(this).apply {
            setText(R.string.retry)
            visibility = View.GONE
            setOnClickListener { connect(p) }
        }
        val unpair = Button(this).apply {
            setText(R.string.unpair)
            setOnClickListener { confirmUnpair() }
        }
        val about = Button(this).apply {
            setText(R.string.about_button)
            setOnClickListener { AboutDialog.show(this@MainActivity) }
        }
        bar.addView(status); bar.addView(retry); bar.addView(about); bar.addView(unpair)

        val progress = ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal).apply {
            max = 100
        }

        val wv = WebView(this).apply {
            visibility = View.GONE
            layoutParams = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f
            )
            settings.javaScriptEnabled = true      // Streamlit needs JS
            settings.domStorageEnabled = true
            settings.allowFileAccess = false
            settings.allowContentAccess = false
            webViewClient = onionOnlyClient(p)
        }

        val notifyRow = SwitchCompat(this).apply {
            setText(R.string.notify_switch)
            setPadding(dp(12), dp(4), dp(12), dp(4))
            isChecked = notifyPrefs.enabled
            setOnCheckedChangeListener { _, checked ->
                if (checked == notifyPrefs.enabled) return@setOnCheckedChangeListener
                if (checked) requestEnableNotifications() else disableNotifications()
            }
        }
        notifySwitch = notifyRow

        col.addView(bar)
        col.addView(notifyRow)
        col.addView(progress)
        col.addView(wv)
        root.addView(col)

        statusText = status; progressBar = progress; retryButton = retry; webView = wv
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
            if (request.isForMainFrame) showError(getString(R.string.page_error))
        }
    }

    private fun loadThroughProxy(host: String, port: Int, p: Pairing) {
        if (!WebViewFeature.isFeatureSupported(WebViewFeature.PROXY_OVERRIDE)) {
            showError(getString(R.string.webview_unsupported))
            return
        }
        // VERIFY: "socks5://" so that Chromium sends the .onion hostname to Tor (remote DNS).
        val cfg = ProxyConfig.Builder().addProxyRule("socks5://$host:$port").build()
        ProxyController.getInstance().setProxyOverride(
            cfg, ContextCompat.getMainExecutor(this)
        ) {
            val wv = webView ?: return@setProxyOverride
            statusText?.text = getString(R.string.connected)
            progressBar?.visibility = View.GONE
            retryButton?.visibility = View.GONE
            wv.visibility = View.VISIBLE
            wv.loadUrl(p.url)
        }
    }

    private fun requestEnableNotifications() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU && !Notifications.hasPermission(this)) {
            notificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
        } else {
            enableNotifications()
        }
    }

    private fun enableNotifications() {
        notifyPrefs.resetCursors()
        notifyPrefs.enabled = true
        Notifications.schedule(applicationContext)
        notifySwitch?.isChecked = true
    }

    private fun disableNotifications() {
        notifyPrefs.enabled = false
        Notifications.cancel(applicationContext)
    }

    private fun showError(message: String) {
        statusText?.text = message
        progressBar?.visibility = View.GONE
        retryButton?.visibility = View.VISIBLE
    }

    private fun confirmUnpair() {
        AlertDialog.Builder(this)
            .setMessage(R.string.unpair_confirm)
            .setPositiveButton(android.R.string.ok) { _, _ ->
                disableNotifications()
                notifyPrefs.resetCursors()
                store.clear()
                (application as App).tor.stop()
                finishAndRemoveTask()
                Process.killProcess(Process.myPid())   // drops the key from Tor's memory too
            }
            .setNegativeButton(android.R.string.cancel, null)
            .show()
    }

    private fun dp(v: Int): Int = (v * resources.displayMetrics.density).toInt()
}
