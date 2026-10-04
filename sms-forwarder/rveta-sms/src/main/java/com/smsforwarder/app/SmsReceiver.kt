package com.smsforwarder.app

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.provider.Telephony
import androidx.work.NetworkType
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.ExistingWorkPolicy
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.workDataOf
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

class SmsReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Telephony.Sms.Intents.SMS_RECEIVED_ACTION) return
        val pending = goAsync()
        Executors.newSingleThreadExecutor().execute {
            try {
                val store = PendingSmsStore.get(context)
                for (msg in SmsParser.parseIntent(intent)) {
                    val id = store.insertIfNew(msg.sender, msg.body, msg.receivedAtMillis, msg.subscriptionId)
                    if (id != null) enqueue(context, id)
                }
                store.cleanup()
            } finally {
                pending.finish()
            }
        }
    }

    companion object {
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
