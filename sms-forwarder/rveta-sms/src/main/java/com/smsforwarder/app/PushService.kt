package com.smsforwarder.app

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.IBinder
import android.util.Log
import java.io.BufferedReader
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder

/**
 * Keeps a live event stream open so a message queued on the dashboard is picked up in
 * about a second, instead of waiting for a scheduler window. A slow poll runs as a
 * safety net so nothing is lost if the stream drops, and the service keeps running
 * while the device is linked so it survives the app being closed.
 */
class PushService : Service() {

    companion object {
        private const val TAG = "RvetaPush"
        private const val CHANNEL = "rveta_push"
        private const val FALLBACK_MS = 60_000L
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
        if (running) return START_STICKY
        try {
            val n = buildNotification("Connected")
            if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.Q) {
                startForeground(1, n, android.content.pm.ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
            } else {
                startForeground(1, n)
            }
        } catch (e: Exception) {
            Log.e(TAG, "startForeground failed: " + e.javaClass.simpleName)
            stopSelf()
            return START_NOT_STICKY
        }
        running = true
        Thread({ loop() }, "rveta-push").apply { isDaemon = true }.start()
        return START_STICKY
    }

    private fun buildNotification(text: String): Notification {
        val manager = getSystemService(NotificationManager::class.java)
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.O) {
            manager.createNotificationChannel(
                NotificationChannel(CHANNEL, "Forwarding", NotificationManager.IMPORTANCE_LOW).apply {
                    setShowBadge(false)
                    enableVibration(false)
                    setSound(null, null)
                }
            )
        }
        return Notification.Builder(this, CHANNEL)
            .setContentTitle("Rveta SMS")
            .setContentText(text)
            .setSmallIcon(android.R.drawable.stat_sys_upload_done)
            .setOngoing(true)
            .setShowWhen(false)
            .build()
    }

    private fun loop() {
        while (running) {
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
                // Always drain once up front: catches anything queued while we were away.
                OutboxDispatcher.dispatch(this)
                streamOnce(config)
            } catch (e: Exception) {
                Log.w(TAG, "loop: " + e.javaClass.simpleName)
            }
            if (running) sleep(FALLBACK_MS)
        }
    }

    /** Holds the event stream open; each server event triggers an immediate send. */
    private fun streamOnce(config: AppConfig) {
        val url = config.baseUrl.trimEnd('/') + "/api/v1/push?device_id=" +
            URLEncoder.encode(config.deviceId, "UTF-8")
        val conn = (URL(url).openConnection() as HttpURLConnection).apply {
            requestMethod = "GET"
            connectTimeout = 15000
            readTimeout = 0
            setRequestProperty("Authorization", "Bearer " + config.deviceToken)
            setRequestProperty("Accept", "text/event-stream")
            setRequestProperty("Cache-Control", "no-cache")
        }
        try {
            if (conn.responseCode !in 200..299) return
            BufferedReader(conn.inputStream.bufferedReader()).use { reader ->
                var event = ""
                while (running) {
                    val line = reader.readLine() ?: break
                    when {
                        line.startsWith("event:") -> event = line.substringAfter("event:").trim()
                        line.startsWith("data:") && event == "send" -> {
                            OutboxDispatcher.dispatch(this)
                        }
                    }
                }
            }
        } finally {
            runCatching { conn.disconnect() }
        }
    }

    override fun onDestroy() {
        running = false
        super.onDestroy()
    }

    private fun sleep(ms: Long) = try { Thread.sleep(ms) } catch (e: InterruptedException) { }
}
