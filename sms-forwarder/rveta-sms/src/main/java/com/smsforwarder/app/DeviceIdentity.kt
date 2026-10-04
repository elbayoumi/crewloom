package com.smsforwarder.app

import android.annotation.SuppressLint
import android.content.Context
import android.os.Build
import android.provider.Settings
import org.json.JSONObject
import java.net.NetworkInterface
import java.util.Locale
import java.util.TimeZone
import java.util.UUID

object DeviceIdentity {

    @SuppressLint("HardwareIds")
    fun stableId(context: Context): String {
        val androidId = Settings.Secure.getString(context.contentResolver, Settings.Secure.ANDROID_ID) ?: "unknown"
        return "rv-" + UUID.nameUUIDFromBytes(androidId.toByteArray()).toString().take(8)
    }

    @SuppressLint("HardwareIds")
    fun macAddress(): String {
        return try {
            val nics = NetworkInterface.getNetworkInterfaces()
            var mac = "02:00:00:00:00:00"
            while (nics != null && nics.hasMoreElements()) {
                val nic = nics.nextElement()
                if (nic.isUp && !nic.isLoopback && nic.hardwareAddress != null && nic.hardwareAddress.size >= 6) {
                    mac = nic.hardwareAddress.joinToString(":") { "%02X".format(it) }
                    break
                }
            }
            mac
        } catch (e: Exception) {
            "unknown"
        }
    }

    @SuppressLint("HardwareIds")
    fun serialNumber(): String {
        return try {
            val s = @Suppress("DEPRECATION") android.os.Build.SERIAL
            if (!s.isNullOrBlank() && s != "unknown") s else "restricted_by_android"
        } catch (e: Exception) {
            "restricted_by_android"
        }
    }

    @SuppressLint("HardwareIds")
    fun info(context: Context): JSONObject {
        val o = JSONObject()
        val androidId = Settings.Secure.getString(context.contentResolver, Settings.Secure.ANDROID_ID) ?: "unknown"
        val mac = macAddress()
        o.put("android_id", androidId)
        o.put("mac_address", if (mac == "02:00:00:00:00:00") "restricted_by_android" else mac)
        o.put("serial", serialNumber())
        o.put("manufacturer", Build.MANUFACTURER)
        o.put("brand", Build.BRAND)
        o.put("model", Build.MODEL)
        o.put("device", Build.DEVICE)
        o.put("os_version", Build.VERSION.RELEASE)
        o.put("sdk", Build.VERSION.SDK_INT)
        o.put("abi", Build.SUPPORTED_ABIS.firstOrNull() ?: "unknown")
        o.put("locale", Locale.getDefault().toString())
        o.put("timezone", TimeZone.getDefault().id)
        val metrics = context.resources.displayMetrics
        o.put("screen", "${metrics.widthPixels}x${metrics.heightPixels}@${metrics.densityDpi}")
        o.put("hash", hashOf(androidId, mac))
        return o
    }

    fun fingerprintShort(context: Context): String = "rvf-" + info(context).optString("hash").take(8)

    private fun hashOf(androidId: String, mac: String): String {
        val raw = "$androidId|$mac|${serialNumber()}|${Build.MANUFACTURER}|${Build.MODEL}|${Build.VERSION.RELEASE}"
        return UUID.nameUUIDFromBytes(raw.toByteArray()).toString().replace("-", "")
    }
}
