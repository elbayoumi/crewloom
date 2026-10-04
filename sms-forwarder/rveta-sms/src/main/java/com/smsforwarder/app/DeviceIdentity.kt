package com.smsforwarder.app

import android.annotation.SuppressLint
import android.content.Context
import android.provider.Settings
import java.util.UUID

object DeviceIdentity {

    @SuppressLint("HardwareIds")
    fun stableId(context: Context): String {
        val androidId = Settings.Secure.getString(context.contentResolver, Settings.Secure.ANDROID_ID) ?: "unknown"
        return "rv-" + UUID.nameUUIDFromBytes(androidId.toByteArray()).toString().take(8)
    }

    fun fingerprint(context: Context): String {
        val androidId = Settings.Secure.getString(context.contentResolver, Settings.Secure.ANDROID_ID) ?: "unknown"
        val model = android.os.Build.MODEL ?: ""
        val release = android.os.Build.VERSION.RELEASE ?: ""
        return "rvf-" + UUID.nameUUIDFromBytes("$androidId|$model|$release".toByteArray()).toString().take(8)
    }
}
