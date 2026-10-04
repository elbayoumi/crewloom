package com.smsforwarder.app

import android.content.Context
import android.telephony.SmsManager
import android.util.Log
import androidx.work.Worker
import androidx.work.WorkerParameters
import java.net.HttpURLConnection
import java.net.URL
import org.json.JSONArray

class OutboxWorker(context: Context, params: WorkerParameters) : Worker(context, params) {

    companion object {
        private const val MAX_ATTEMPTS = 10
    }

    override fun doWork(): Result {
        val config = AppConfig(applicationContext)
        if (config.baseUrl.isBlank() || config.deviceToken.isBlank()) return Result.success()
        return try {
            val list = getPending(config.baseUrl, config.deviceToken, config.deviceId)
            for (i in 0 until list.length()) {
                val o = list.getJSONObject(i)
                val id = o.getLong("id")
                val to = o.getString("to")
                val body = o.getString("body")
                val ok = try {
                    SmsManager.getDefault().sendTextMessage(to, null, body, null, null)
                    true
                } catch (e: Exception) { false }
                postResult(config.baseUrl, config.deviceToken, id, if (ok) "sent" else "send_failed")
            }
            Result.success()
        } catch (e: Exception) {
            if (runAttemptCount >= MAX_ATTEMPTS) Result.success() else Result.retry()
        }
    }

    private fun getPending(baseUrl: String, token: String, deviceId: String): JSONArray {
        val conn = (URL(baseUrl.trimEnd('/') + "/api/v1/outbox?device_id=" + java.net.URLEncoder.encode(deviceId, "UTF-8")).openConnection() as HttpURLConnection).apply {
            requestMethod = "GET"
            connectTimeout = 15000
            readTimeout = 20000
            setRequestProperty("Authorization", "Bearer $token")
        }
        return try {
            if (conn.responseCode !in 200..299) JSONArray() else JSONArray(conn.inputStream.bufferedReader().readText())
        } catch (e: Exception) {
            JSONArray()
        } finally {
            runCatching { conn.errorStream?.close() }
            conn.disconnect()
        }
    }

    private fun postResult(baseUrl: String, token: String, id: Long, status: String) {
        try {
            val conn = (URL(baseUrl.trimEnd('/') + "/api/v1/outbox/$id/result").openConnection() as HttpURLConnection).apply {
                requestMethod = "POST"
                connectTimeout = 15000
                readTimeout = 20000
                doOutput = true
                setRequestProperty("Authorization", "Bearer $token")
                setRequestProperty("Content-Type", "application/json")
            }
            conn.outputStream.use { it.write(org.json.JSONObject().put("status", status).toString().toByteArray(Charsets.UTF_8)) }
            conn.responseCode
            conn.disconnect()
        } catch (e: Exception) { Log.w("Outbox", "result post failed") }
    }
}
