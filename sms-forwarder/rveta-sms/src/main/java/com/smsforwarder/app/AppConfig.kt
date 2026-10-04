package com.smsforwarder.app

import android.content.Context
import android.content.SharedPreferences

class AppConfig(context: Context) {

    private val prefs: SharedPreferences = context.getSharedPreferences("config", Context.MODE_PRIVATE)

    private val securePrefs: SharedPreferences? = try {
        val masterKey = androidx.security.crypto.MasterKey.Builder(context)
            .setKeyScheme(androidx.security.crypto.MasterKey.KeyScheme.AES256_GCM)
            .build()
        androidx.security.crypto.EncryptedSharedPreferences.create(
            context,
            "secure_config",
            masterKey,
            androidx.security.crypto.EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            androidx.security.crypto.EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
        )
    } catch (e: Exception) {
        null
    }

    var tokenStoreError: String? = if (securePrefs == null) "encrypted_store_unavailable" else null

    var baseUrl: String
        get() = prefs.getString("base_url", "") ?: ""
        set(value) = prefs.edit().putString("base_url", value.trim()).apply()

    var deviceId: String
        get() = prefs.getString("device_id", "") ?: ""
        set(value) = prefs.edit().putString("device_id", value.trim()).apply()

    var deviceToken: String
        get() = securePrefs?.getString("device_token", "") ?: ""
        set(value) {
            securePrefs?.edit()?.putString("device_token", value.trim())?.apply()
        }
}
