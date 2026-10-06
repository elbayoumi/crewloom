package com.smsforwarder.app

import android.content.Context
import android.telephony.SmsManager
import android.util.Log
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import org.json.JSONArray
import org.json.JSONObject

/**
 * Sends queued outbound SMS. Callable directly from the live push connection
 * (sub-second) or from the periodic WorkManager fallback (delayed but reliable).
 */
object OutboxDispatcher {

    private const val TAG = "RvetaOutbox"

    fun dispatch(context: Context): Int {
        OutboundReporter.sweepUnconfirmed(context)
        val config = AppConfig(context)
        if (config.baseUrl.isBlank() || config.deviceToken.isBlank() || config.deviceId.isBlank()) return 0
        return try {
            val list = fetch(config.baseUrl, config.deviceToken, config.deviceId)
            var sent = 0
            for (i in 0 until list.length()) {
                val o = list.getJSONObject(i)
                val id = o.getLong("id")
                val to = o.getString("to")
                val body = o.getString("body")
                // Ask the carrier for the real outcome instead of assuming success.
                val ok = try {
                    PendingSmsStore.get(context).trackOutbound(id, "queued")
                    OutboundReporter.report(context, id, "queued")
                    SmsManager.getDefault().sendTextMessage(
                        to, null, body,
                        OutboundStatusReceiver.sentIntent(context, id),
                        OutboundStatusReceiver.deliveredIntent(context, id)
                    )
                    true
                } catch (e: Exception) {
                    Log.w(TAG, "send failed: ${e.javaClass.simpleName}")
                    PendingSmsStore.get(context).trackOutbound(id, "send_failed")
                    report(config.baseUrl, config.deviceToken, id, "send_failed")
                    false
                }
                if (ok) sent++
            }
            sent
        } catch (e: Exception) {
            Log.w(TAG, "dispatch failed: ${e.javaClass.simpleName}")
            -1
        }
    }

    private fun fetch(baseUrl: String, token: String, deviceId: String): JSONArray {
        val conn = (URL(
            baseUrl.trimEnd('/') + "/api/v1/outbox?device_id=" + URLEncoder.encode(deviceId, "UTF-8")
        ).openConnection() as HttpURLConnection).apply {
            requestMethod = "GET"
            connectTimeout = 10000
            readTimeout = 15000
            setRequestProperty("Authorization", "Bearer $token")
        }
        return try {
            if (conn.responseCode !in 200..299) JSONArray() else JSONArray(conn.inputStream.bufferedReader().readText())
        } finally {
            runCatching { conn.errorStream?.close() }
            conn.disconnect()
        }
    }

    private fun report(baseUrl: String, token: String, id: Long, status: String) {
        try {
            val conn = (URL(baseUrl.trimEnd('/') + "/api/v1/outbox/$id/result").openConnection() as HttpURLConnection).apply {
                requestMethod = "POST"
                doOutput = true
                connectTimeout = 10000
                readTimeout = 10000
                setRequestProperty("Authorization", "Bearer $token")
                setRequestProperty("Content-Type", "application/json")
            }
            conn.outputStream.use {
                it.write(JSONObject().put("status", status).toString().toByteArray(Charsets.UTF_8))
            }
            conn.responseCode
            conn.disconnect()
        } catch (e: Exception) {
            Log.w(TAG, "result report failed")
        }
    }
}
