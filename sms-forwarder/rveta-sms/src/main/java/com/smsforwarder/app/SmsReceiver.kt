package com.smsforwarder.app

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.provider.Telephony
import android.util.Log
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.workDataOf
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

class SmsReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Telephony.Sms.Intents.SMS_RECEIVED_ACTION) return
        val pending = goAsync()
        val app = context.applicationContext
        EXECUTOR.execute {
            try {
                val store = PendingSmsStore.get(app)
                for (msg in SmsParser.parseIntent(intent)) {
                    val id = store.insertIfNew(msg.sender, msg.body, msg.receivedAtMillis, msg.subscriptionId, null)
                    if (id != null) {
                        // Try immediately so the message reaches the backend in the same second.
                        val delivered = InboundDispatcher.deliver(app, id)
                        if (!delivered) enqueue(app, id)
                    }
                }
                store.cleanup()
                RvetaSms.checkOutbox(app)
                TickerWorker.kick(app)
            } catch (e: Exception) {
                // Never let a background failure kill the process mid-broadcast.
                Log.w(TAG, "sms receive failed: ${e.javaClass.simpleName}")
            } finally {
                pending.finish()
            }
        }
    }

    companion object {
        private const val TAG = "RvetaSms"
        private val EXECUTOR = Executors.newSingleThreadExecutor { r ->
            Thread(r, "rveta-sms-receiver").apply { isDaemon = true }
        }

        fun enqueue(context: Context, messageId: String) {
            val constraints = Constraints.Builder()
                .setRequiredNetworkType(NetworkType.CONNECTED)
                .build()
            val request = OneTimeWorkRequestBuilder<SmsForwardWorker>()
                .setInputData(workDataOf(SmsForwardWorker.KEY_MESSAGE_ID to messageId))
                .setConstraints(constraints)
                .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
                .build()
            WorkManager.getInstance(context).enqueueUniqueWork(
                "sms_" + messageId,
                ExistingWorkPolicy.KEEP,
                request
            )
        }
    }
}
