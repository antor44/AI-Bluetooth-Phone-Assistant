package com.aiphone.switchboard

import android.content.Context
import android.net.Uri
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey

/**
 * Pairing data produced by onion_poc.py on the switchboard:
 *   aiphone://pair?onion=<56 chars>.onion&key=<52 chars base32>
 * or the Tor client-auth line:
 *   <56 chars>:descriptor:x25519:<52 chars base32>
 */
data class Pairing(val onion: String, val key: String) {

    /** 56-character v3 address without ".onion". */
    val host: String get() = onion.removeSuffix(".onion")

    /** Content of a Tor client-auth file (.auth_private) in ClientOnionAuthDir. */
    val authLine: String get() = "$host:descriptor:x25519:$key"

    val url: String get() = "http://$onion/"

    companion object {
        private val HOST_RE = Regex("^[a-z2-7]{56}$")
        private val KEY_RE = Regex("^[A-Z2-7]{52}$")

        fun parse(raw: String): Pairing? {
            val text = raw.trim()
            if (text.startsWith("aiphone://", ignoreCase = true)) {
                val uri = Uri.parse(text)
                return build(uri.getQueryParameter("onion"), uri.getQueryParameter("key"))
            }
            val parts = text.split(":")
            if (parts.size == 4 && parts[1] == "descriptor" && parts[2] == "x25519") {
                return build(parts[0], parts[3])
            }
            return null
        }

        fun build(onionRaw: String?, keyRaw: String?): Pairing? {
            val host = onionRaw?.trim()?.lowercase()
                ?.removePrefix("http://")?.removeSuffix("/")?.removeSuffix(".onion")
                ?: return null
            val key = keyRaw?.trim()?.uppercase() ?: return null
            if (!HOST_RE.matches(host) || !KEY_RE.matches(key)) return null
            return Pairing("$host.onion", key)
        }
    }
}

/** Stores the pairing (including the private key) encrypted with the Android Keystore. */
class PairingStore(context: Context) {
    private val prefs = EncryptedSharedPreferences.create(
        context,
        "pairing",
        MasterKey.Builder(context).setKeyScheme(MasterKey.KeyScheme.AES256_GCM).build(),
        EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
        EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
    )

    fun load(): Pairing? = Pairing.build(prefs.getString("onion", null), prefs.getString("key", null))

    fun save(p: Pairing) {
        prefs.edit().putString("onion", p.onion).putString("key", p.key).apply()
    }

    fun clear() {
        prefs.edit().clear().apply()
    }
}
