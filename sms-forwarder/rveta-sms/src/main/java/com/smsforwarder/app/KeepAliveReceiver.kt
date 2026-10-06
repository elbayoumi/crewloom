package com.smsforwarder.app

import android.app.AlarmManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log
import java.net.HttpURLConnection
import java.net.URL

/**
 * Watchdog.
 *
 * Even a foreground service can be killed by aggressive OEM process managers
 * (Realme/Oppo/Xiaomi). This alarm re-arms itself on every fire, restarts the
 * send service when it is gone, and reports a heartbeat so the dashboard can
 * tell whether the phone is actually still reachable.
 */
class KeepAliveReceiver : BroadcastReceiver() {

    companion object {
        private const val TAG = "RvetaKeepAlive"
        private const val INTERVAL_MS = 60_000L
        const val ACTION = "com.smsforwarder.app.KEEP_ALIVE"
        private const val REQ = 4242

        fun arm(context: Context) {
            val am = context.getSystemService(Context.ALARM_SERVICE) as? AlarmManager ?: return
            val pi = PendingIntent.getBroadcast(
                context, REQ,
                Intent(context, KeepAliveReceiver::class.java).setAction(ACTION),
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )
            // Inexact alarms still fire during Doze and need no special permission,
            // which keeps this working on Android 15 where exact alarms are restricted.
            runCatching {
                am.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, System.currentTimeMillis() + INTERVAL_MS, pi)
            }.onFailure { Log.w(TAG, "alarm failed: " + it.javaClass.simpleName) }
        }

        fun cancel(context: Context) {
            val am = context.getSystemService(Context.ALARM_SERVICE) as? AlarmManager ?: return
            val pi = PendingIntent.getBroadcast(
                context, REQ,
                Intent(context, KeepAliveReceiver::class.java).setAction(ACTION),
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )
            runCatching { am.cancel(pi) }
        }
    }

    override fun onReceive(context: Context, intent: Intent) {
        val app = context.applicationContext
        Log.i(TAG, "watchdog fired")
        try {
            if (PushService.isEnabled(app)) PushService.start(app)
            heartbeat(app)
        } catch (e: Exception) {
            Log.w(TAG, "keepalive: " + e.javaClass.simpleName)
        } finally {
            arm(app)
        }
    }

    /** Lets the dashboard show whether the phone is alive and when it was last seen. */
    private fun heartbeat(context: Context) {
        val config = AppConfig(context)
        if (config.deviceId.isBlank() || config.deviceToken.isBlank() || config.baseUrl.isBlank()) return
        Thread {
            try {
                val conn = (URL(config.baseUrl.trimEnd('/') + "/api/v1/heartbeat").openConnection() as HttpURLConnection).apply {
                    requestMethod = "POST"
                    doOutput = true
                    connectTimeout = 8000
                    readTimeout = 8000
                    setRequestProperty("Authorization", "Bearer " + config.deviceToken)
                    setRequestProperty("Content-Type", "application/json")
                }
                val body = org.json.JSONObject().put("device_id", config.deviceId).toString()
                conn.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
                val code = conn.responseCode
                conn.disconnect()
                Log.i(TAG, "heartbeat $code for ${config.deviceId}")
            } catch (e: Exception) {
                // network may be down; the queue on the server keeps messages safe
            }
        }.start()
    }
}
