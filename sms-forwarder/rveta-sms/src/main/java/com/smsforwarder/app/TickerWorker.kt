package com.smsforwarder.app

import android.content.Context
import androidx.work.BackoffPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.Worker
import androidx.work.WorkerParameters
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.util.concurrent.TimeUnit

/**
 * Keeps the device reachable while the app is closed.
 *
 * WorkManager periodic work cannot run faster than every 15 minutes, so instead we
 * chain short one-shot jobs. Each tick checks whether a web dashboard is open and,
 * if so, starts the fast-send service; otherwise it simply drains the outbox and
 * schedules the next tick. This keeps sending responsive without a permanent
 * foreground service or push infrastructure.
 */
class TickerWorker(context: Context, params: WorkerParameters) : Worker(context, params) {

    companion object {
        private const val UNIQUE = "rveta_ticker"
        private const val FAST_MS = 60 * 1000L     // fast-send enabled
        private const val SLOW_MS = 5 * 60 * 1000L  // fast-send disabled

        fun kick(context: Context) {
            schedule(context, 5_000L)
        }

        fun schedule(context: Context, delayMs: Long) {
            val request = OneTimeWorkRequestBuilder<TickerWorker>()
                .setInitialDelay(delayMs, TimeUnit.MILLISECONDS)
                .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
                .build()
            WorkManager.getInstance(context)
                .enqueueUniqueWork(UNIQUE, ExistingWorkPolicy.REPLACE, request)
        }
    }

    override fun doWork(): Result {
        val config = AppConfig(applicationContext)
        var next = SLOW_MS
        try {
            if (config.deviceId.isNotBlank() && config.deviceToken.isNotBlank() && config.baseUrl.isNotBlank()) {
                if (PushService.isEnabled(applicationContext)) {
                    // Keep the fast-send service alive so it survives the app being closed.
                    PushService.start(applicationContext)
                    next = FAST_MS
                } else {
                    OutboxDispatcher.dispatch(applicationContext)
                    next = SLOW_MS
                }
            }
        } catch (e: Exception) {
            // never crash the ticker; try again on the slow cadence
            next = SLOW_MS
        }
        schedule(applicationContext, next)
        return Result.success()
    }

    private fun checkDashboard(config: AppConfig): Boolean {
        val url = config.baseUrl.trimEnd('/') + "/api/v1/push/status?device_id=" +
            URLEncoder.encode(config.deviceId, "UTF-8")
        val conn = (URL(url).openConnection() as HttpURLConnection).apply {
            requestMethod = "GET"
            connectTimeout = 10000
            readTimeout = 10000
            setRequestProperty("Authorization", "Bearer " + config.deviceToken)
        }
        return try {
            if (conn.responseCode !in 200..299) false
            else org.json.JSONObject(conn.inputStream.bufferedReader().readText())
                .optBoolean("dashboard_open", false)
        } catch (e: Exception) {
            false
        } finally {
            runCatching { conn.errorStream?.close() }
            conn.disconnect()
        }
    }
}
