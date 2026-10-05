package com.smsforwarder.app

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.IBinder
import android.util.Log
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder

/**
 * Fast-send mode. While the web dashboard is open, the device polls a tiny status
 * endpoint on a short interval and drains the outbox immediately, so a message sent
 * from the dashboard reaches the phone within seconds instead of waiting for the
 * periodic WorkManager window. The service stops itself when no dashboard is open,
 * so the app never holds a permanent foreground service.
 */
class PushService : Service() {

    companion object {
        private const val TAG = "RvetaPush"
        private const val CHANNEL = "rveta_push"
        private const val POLL_FAST_MS = 3000L    // dashboard open -> seconds
        private const val POLL_SLOW_MS = 60_000L   // idle -> once a minute
        private const val PREFS = "runtime"
        const val KEY_FAST_SEND = "fast_send_enabled"

        fun isEnabled(context: Context): Boolean =
            context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getBoolean(KEY_FAST_SEND, true)

        fun setEnabled(context: Context, enabled: Boolean) {
            context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().putBoolean(KEY_FAST_SEND, enabled).apply()
            if (enabled) start(context) else stop(context)
        }

        fun start(context: Context) {
            val intent = Intent(context, PushService::class.java)
            runCatching {
                if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.O) {
                    context.startForegroundService(intent)
                } else {
                    context.startService(intent)
                }
            }
        }

        fun stop(context: Context) {
            runCatching { context.stopService(Intent(context, PushService::class.java)) }
        }
    }

    @Volatile
    private var running = false

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        try {
            if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.Q) {
                startForeground(1, buildNotification("Instant send active"), android.content.pm.ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
            } else {
                startForeground(1, buildNotification("Instant send active"))
            }
        } catch (e: Exception) {
            Log.e(TAG, "startForeground failed: " + e.javaClass.simpleName)
            stopSelf()
            return START_NOT_STICKY
        }
        if (running) return START_STICKY
        running = true
        Thread({ loop() }, "rveta-push").apply { isDaemon = true }.start()
        return START_STICKY
    }

    private fun buildNotification(text: String): Notification {
        val manager = getSystemService(NotificationManager::class.java)
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.O) {
            manager.createNotificationChannel(
                NotificationChannel(CHANNEL, "Forwarding", NotificationManager.IMPORTANCE_LOW)
            )
        }
        return Notification.Builder(this, CHANNEL)
            .setContentTitle("Rveta SMS")
            .setContentText(text)
            .setSmallIcon(android.R.drawable.stat_sys_upload_done)
            .setOngoing(true)
            .build()
    }

    private fun dashboardOpen(config: AppConfig): Boolean {
        val url = config.baseUrl.trimEnd('/') + "/api/v1/push/status?device_id=" +
            URLEncoder.encode(config.deviceId, "UTF-8")
        val conn = (URL(url).openConnection() as HttpURLConnection).apply {
            requestMethod = "GET"
            connectTimeout = 8000
            readTimeout = 8000
            setRequestProperty("Authorization", "Bearer " + config.deviceToken)
        }
        return try {
            if (conn.responseCode !in 200..299) false
            else JSONObject(conn.inputStream.bufferedReader().readText()).optBoolean("dashboard_open", false)
        } catch (e: Exception) {
            false
        } finally {
            runCatching { conn.errorStream?.close() }
            conn.disconnect()
        }
    }

    private fun loop() {
        while (running) {
            var wait = POLL_SLOW_MS
            try {
                if (!isEnabled(this)) {
                    stopSelf()
                    return
                }
                val config = AppConfig(this)
                if (config.deviceId.isBlank() || config.deviceToken.isBlank() || config.baseUrl.isBlank()) {
                    sleep(10_000)
                    continue
                }
                if (dashboardOpen(config)) {
                    // Dashboard in use: deliver in seconds.
                    OutboxDispatcher.dispatch(this)
                    wait = POLL_FAST_MS
                } else {
                    // Idle: still deliver queued messages, just less often.
                    OutboxDispatcher.dispatch(this)
                    wait = POLL_SLOW_MS
                }
            } catch (e: Exception) {
                Log.w(TAG, "loop: " + e.javaClass.simpleName)
            }
            sleep(wait)
        }
    }

    override fun onDestroy() {
        running = false
        super.onDestroy()
    }

    private fun sleep(ms: Long) = try { Thread.sleep(ms) } catch (e: InterruptedException) { }
}
