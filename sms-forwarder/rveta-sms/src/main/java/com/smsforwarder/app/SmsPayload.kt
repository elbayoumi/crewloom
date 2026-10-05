package com.smsforwarder.app

import java.text.SimpleDateFormat
import java.util.Locale
import java.util.TimeZone
import java.util.SimpleTimeZone

data class SmsPayload(
    val sender: String,
    val message: String,
    val receivedAt: String,
    val deviceId: String,
    val messageId: String,
    val senderName: String? = null,
    val deviceInfo: String? = null
) {
    fun toJson(): String {
        val o = org.json.JSONObject()
        o.put("sender", sender)
        o.put("message", message)
        o.put("received_at", receivedAt)
        o.put("device_id", deviceId)
        o.put("message_id", messageId)
        if (!senderName.isNullOrBlank()) o.put("sender_name", senderName)
        if (!deviceInfo.isNullOrBlank()) o.put("device_info", deviceInfo)
        return o.toString()
    }

    companion object {
        fun formatTimestamp(millis: Long): String {
            val sdf = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ssXXX", Locale.US)
            sdf.timeZone = TimeZone.getDefault()
            return sdf.format(java.util.Date(millis))
        }
    }
}
