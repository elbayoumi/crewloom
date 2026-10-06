package com.smsforwarder.app

import android.content.Context
import android.util.Log
import java.net.HttpURLConnection
import java.net.URL
import org.json.JSONObject

/** Pushes the true outbound state to the dashboard. */
object OutboundReporter {

    fun report(context: Context, outId: Long, status: String) {
        val config = AppConfig(context)
        if (config.baseUrl.isBlank() || config.deviceToken.isBlank()) return
        Thread {
            try {
                val conn = (URL(config.baseUrl.trimEnd('/') + "/api/v1/outbox/$outId/result").openConnection() as HttpURLConnection).apply {
                    requestMethod = "POST"
                    doOutput = true
                    connectTimeout = 10000
                    readTimeout = 10000
                    setRequestProperty("Authorization", "Bearer " + config.deviceToken)
                    setRequestProperty("Content-Type", "application/json")
                }
                val body = JSONObject()
                    .put("status", status)
                    .put("device_id", config.deviceId)
                    .toString()
                conn.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
                conn.responseCode
                conn.disconnect()
                if (status == "delivered" || status == "not_delivered" || status == "rejected") {
                    PendingSmsStore.get(context).clearOutbound(outId)
                }
            } catch (e: Exception) {
                Log.w("RvetaOut", "report failed")
            }
        }.start()
    }

    /**
     * Many operators never send a delivery report. Anything still unconfirmed after
     * this long is marked as "handed over, unconfirmed" instead of silently claiming
     * delivery.
     */
    fun sweepUnconfirmed(context: Context) {
        val store = PendingSmsStore.get(context)
        for (id in store.pendingOutboundIds()) {
            if (store.outboundStatus(id) == "accepted") {
                store.trackOutbound(id, "unconfirmed")
                report(context, id, "unconfirmed")
            }
        }
    }
}
