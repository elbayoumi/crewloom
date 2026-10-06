package com.smsforwarder.app

import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.telephony.SmsManager
import android.util.Log
import java.util.concurrent.Executors

/**
 * Reports the real outcome of an outbound SMS.
 *
 * "sent" in the dashboard previously meant only "handed to the radio". These two
 * callbacks give the carrier's actual answer:
 *  - SENT: the radio accepted the message for the network
 *  - DELIVERED: the network confirmed delivery to the handset
 * so the dashboard never claims a message went out before it actually did.
 */
class OutboundStatusReceiver : BroadcastReceiver() {

    companion object {
        const val EXTRA_OUT_ID = "out_id"
        const val ACTION_SENT = "com.smsforwarder.app.OUTBOUND_SENT"
        const val ACTION_DELIVERED = "com.smsforwarder.app.OUTBOUND_DELIVERED"
        private val EXECUTOR = Executors.newSingleThreadExecutor { r ->
            Thread(r, "rveta-outbound").apply { isDaemon = true }
        }

        fun sentIntent(context: Context, outId: Long): PendingIntent {
            val intent = Intent(context, OutboundStatusReceiver::class.java).apply {
                action = ACTION_SENT
                putExtra(EXTRA_OUT_ID, outId)
            }
            return PendingIntent.getBroadcast(
                context, outId.toInt(), intent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )
        }

        fun deliveredIntent(context: Context, outId: Long): PendingIntent {
            val intent = Intent(context, OutboundStatusReceiver::class.java).apply {
                action = ACTION_DELIVERED
                putExtra(EXTRA_OUT_ID, outId)
            }
            return PendingIntent.getBroadcast(
                context, outId.toInt() + 100000, intent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )
        }
    }

    override fun onReceive(context: Context, intent: Intent) {
        val outId = intent.getLongExtra(EXTRA_OUT_ID, -1L)
        if (outId <= 0) return
        val app = context.applicationContext
        EXECUTOR.execute {
            try {
                when (intent.action) {
                    ACTION_SENT -> {
                        val code = resultCode
                        val ok = code == ActivityResultOk
                        val status = if (ok) "accepted" else "rejected"
                        PendingSmsStore.get(app).trackOutbound(outId, status)
                        OutboundReporter.report(app, outId, status)
                        Log.i("RvetaOut", "outbound $outId -> $status (code=$code)")
                    }
                    ACTION_DELIVERED -> {
                        val ok = intent.getIntExtra("delivery_status", -1) == 0 ||
                            resultCode == ActivityResultOk
                        val status = if (ok) "delivered" else "not_delivered"
                        PendingSmsStore.get(app).trackOutbound(outId, status)
                        OutboundReporter.report(app, outId, status)
                        Log.i("RvetaOut", "outbound $outId -> $status")
                    }
                }
            } catch (e: Exception) {
                Log.w("RvetaOut", "status failed: " + e.javaClass.simpleName)
            }
        }
    }

    private val ActivityResultOk = android.app.Activity.RESULT_OK
}
